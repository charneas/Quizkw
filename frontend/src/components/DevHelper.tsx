import { createTeam } from '../services/api';

interface DevHelperProps {
  code: string;
}

export default function DevHelper({ code }: DevHelperProps) {
  const handleFastTrack = async () => {
    try {
      // 1. Create teams
      await createTeam(code, { name: 'Dev Team 1' });
      await createTeam(code, { name: 'Dev Team 2' });
      
      // 2. Alert user about backend limitation
      alert('Teams created! Note: your backend `start_game` likely fails if players are not associated with teams. Please add players via UI.');
      
    } catch (err) {
      console.error(err);
      alert('Failed: ' + (err instanceof Error ? err.message : 'Unknown error'));
    }
  };

  return (
    // En flux normal (pas `fixed`) : les deux pages qui l'utilisent (Lobby,
    // Game) ont déjà du contenu dans tous les coins de l'écran selon la
    // largeur, donc n'importe quelle position fixe finissait par chevaucher
    // un titre ou un bouton sur petit écran. Outil dev-only (import.meta.env.DEV),
    // pousser le contenu de quelques pixels en dev n'a pas d'impact réel.
    <div className="mb-3 text-center">
      <button
        onClick={handleFastTrack}
        className="bg-red-600 hover:bg-red-700 text-white px-3 py-2 rounded-lg text-xs font-bold"
      >
        DEV: Fast Track Setup
      </button>
    </div>
  );
}
