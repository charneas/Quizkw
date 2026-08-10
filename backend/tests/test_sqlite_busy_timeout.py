"""BUG-101f : sans PRAGMA busy_timeout, une deuxieme connexion SQLite qui
tente d'ecrire pendant qu'une premiere tient le verrou fichier echoue
immediatement avec "database is locked" (OperationalError -> 500 cote
client), meme pour une action de jeu legitime sans rapport avec les courses
applicatives deja corrigees par #3/#53. Teste directement le mecanisme SQLite
sous-jacent (pas de fenetre de course a esperer via l'ORM/l'app, contrairement
aux autres tests de concurrence du repo) pour un resultat deterministe."""
import os
import sqlite3
import tempfile
import threading
import time


def _hold_write_lock(db_path, hold_seconds, ready_event):
    conn = sqlite3.connect(db_path, timeout=0)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE t SET value = value + 1 WHERE id = 1")
    ready_event.set()
    time.sleep(hold_seconds)
    conn.commit()
    conn.close()


def _make_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value INTEGER)")
    conn.execute("INSERT INTO t (id, value) VALUES (1, 0)")
    conn.commit()
    conn.close()


def test_concurrent_write_fails_immediately_without_busy_timeout():
    """Caracterise le bug avant fix : timeout=0 (comportement par defaut du
    driver sqlite3, celui que l'app avait avant ce fix) leve immediatement."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _make_db(db_path)
        ready = threading.Event()
        holder = threading.Thread(target=_hold_write_lock, args=(db_path, 0.5, ready))
        holder.start()
        ready.wait(timeout=2)

        second = sqlite3.connect(db_path, timeout=0)  # pas de busy_timeout
        try:
            with __import__("pytest").raises(sqlite3.OperationalError, match="locked"):
                second.execute("UPDATE t SET value = value + 1 WHERE id = 1")
        finally:
            second.close()
            holder.join()
    finally:
        os.remove(db_path)


def test_concurrent_write_serializes_with_busy_timeout_instead_of_failing():
    """Avec PRAGMA busy_timeout (le fix), la deuxieme connexion attend que la
    premiere libere le verrou au lieu d'echouer immediatement."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _make_db(db_path)
        ready = threading.Event()
        hold_seconds = 0.5
        holder = threading.Thread(target=_hold_write_lock, args=(db_path, hold_seconds, ready))
        holder.start()
        ready.wait(timeout=2)

        second = sqlite3.connect(db_path, timeout=0)
        second.execute("PRAGMA busy_timeout = 5000")  # même valeur que database.py
        start = time.monotonic()
        second.execute("UPDATE t SET value = value + 1 WHERE id = 1")
        second.commit()
        elapsed = time.monotonic() - start
        second.close()
        holder.join()

        # A bien attendu (pas echoue immediatement) plutot que de lever.
        assert elapsed >= hold_seconds * 0.5

        conn = sqlite3.connect(db_path)
        value = conn.execute("SELECT value FROM t WHERE id = 1").fetchone()[0]
        conn.close()
        assert value == 2  # les 2 écritures ont bien été appliquées, aucune perdue
    finally:
        os.remove(db_path)


def test_app_engine_applies_busy_timeout_pragma():
    """Verifie que app.database configure bien le PRAGMA sur ses connexions
    reelles (pas seulement dans un test isole qui reimplemente le mecanisme)."""
    from app.database import engine

    with engine.connect() as conn:
        raw_conn = conn.connection.dbapi_connection
        cursor = raw_conn.cursor()
        cursor.execute("PRAGMA busy_timeout")
        value = cursor.fetchone()[0]
        cursor.close()
        assert value == 5000