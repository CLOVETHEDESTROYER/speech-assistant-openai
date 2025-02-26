import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface Transcript {
  id: number;
  call_sid: string;
  direction: string;
  scenario: string;
  transcript: string;
  created_at: string;
}

export const TranscriptViewer: React.FC = () => {
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTranscripts = async () => {
      try {
        const response = await axios.get('/api/transcripts/', {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`
          }
        });
        setTranscripts(response.data);
      } catch (err) {
        setError('Failed to load transcripts');
      } finally {
        setLoading(false);
      }
    };

    fetchTranscripts();
  }, []);

  if (loading) return <div>Loading transcripts...</div>;
  if (error) return <div className="text-red-500">{error}</div>;

  return (
    <div className="container mx-auto p-4">
      <h2 className="text-2xl font-bold mb-4">Conversation Transcripts</h2>
      <div className="space-y-4">
        {transcripts.map((transcript) => (
          <div key={transcript.id} className="border p-4 rounded-lg">
            <div className="flex justify-between mb-2">
              <span className="font-semibold">
                {transcript.direction === 'incoming' ? 'Incoming Call' : 'Outgoing Call'}
              </span>
              <span className="text-gray-500">
                {new Date(transcript.created_at).toLocaleString()}
              </span>
            </div>
            <div className="text-sm text-gray-600 mb-2">
              Scenario: {transcript.scenario}
            </div>
            <pre className="whitespace-pre-wrap bg-gray-50 p-3 rounded">
              {transcript.transcript}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}; 