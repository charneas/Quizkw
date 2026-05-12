import { createTeam, startGame } from '../services/api';

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
    <button 
      onClick={handleFastTrack}
      className="fixed top-4 left-4 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg z-50 text-sm font-bold"
    >
      DEV: Fast Track Setup
    </button>
  );
}
