import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

interface Transcript {
  id: number;
  transcript_sid: string;
  status: string;
  full_text: string;
  date_created: string;
  duration: number;
  language_code: string;
}

export const TranscriptList: React.FC = () => {
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTranscripts = async () => {
      try {
        setLoading(true);
        const response = await axios.get('/stored-transcripts/', {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`
          }
        });
        setTranscripts(response.data);
      } catch (err) {
        setError('Failed to load transcripts');
        console.error('Error fetching transcripts:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchTranscripts();
  }, []);

  // Format duration from seconds to minutes:seconds
  const formatDuration = (seconds: number) => {
    if (!seconds) return '0:00';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  if (loading) return <div className="p-4">Loading transcripts...</div>;
  if (error) return <div className="p-4 text-red-500">{error}</div>;
  if (transcripts.length === 0) return <div className="p-4">No transcripts found</div>;

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold mb-6">Your Transcripts</h2>
      
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Transcript ID
              </th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Created
              </th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Duration
              </th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Language
              </th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {transcripts.map((transcript) => (
              <tr key={transcript.transcript_sid} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {transcript.transcript_sid.substring(0, 10)}...
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <span className={`px-2 py-1 rounded-full text-xs ${
                    transcript.status === 'completed' ? 'bg-green-100 text-green-800' : 
                    transcript.status === 'failed' ? 'bg-red-100 text-red-800' : 
                    'bg-yellow-100 text-yellow-800'
                  }`}>
                    {transcript.status}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {new Date(transcript.date_created).toLocaleString()}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {formatDuration(transcript.duration)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {transcript.language_code}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  <Link 
                    to={`/stored-transcripts/${transcript.transcript_sid}`} 
                    className="text-indigo-600 hover:text-indigo-900"
                  >
                    View Details
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}; 