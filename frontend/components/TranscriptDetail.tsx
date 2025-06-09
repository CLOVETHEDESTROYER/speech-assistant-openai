import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface TwilioSentence {
  text: string;
  speaker: number;
  start_time: number;
  end_time: number;
  confidence: number;
}

interface TwilioTranscriptDetail {
  sid: string;
  status: string;
  date_created: string;
  date_updated: string;
  duration: number;
  language_code: string;
  sentences: TwilioSentence[];
}

interface LegacySentence {
  transcript: string;
  speaker: string;
  start_time: number;
  end_time: number;
  confidence: number;
}

interface LegacyTranscriptDetail {
  id: number;
  transcript_sid: string;
  status: string;
  full_text: string;
  date_created: string;
  date_updated: string;
  duration: number;
  language_code: string;
  created_at: string;
  sentences: LegacySentence[];
}

interface TranscriptDetailProps {
  transcriptSid: string;
}

export const TranscriptDetailView: React.FC<TranscriptDetailProps> = ({ transcriptSid }) => {
  const [transcript, setTranscript] = useState<TwilioTranscriptDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTranscript = async () => {
      try {
        setLoading(true);
        
        // Try the new stored-twilio-transcripts endpoint first
        try {
          const response = await axios.get(`/stored-twilio-transcripts/${transcriptSid}`, {
            headers: {
              Authorization: `Bearer ${localStorage.getItem('access_token')}`
            }
          });
          
          // Handle Twilio API format response directly
          setTranscript(response.data);
          return;
        } catch (newEndpointError) {
          console.log('New endpoint failed, falling back to legacy:', newEndpointError);
        }
        
        // Fallback to legacy stored-transcripts endpoint
        const legacyResponse = await axios.get(`/stored-transcripts/${transcriptSid}`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`
          }
        });
        
        // Transform legacy format to Twilio format
        const legacy: LegacyTranscriptDetail = legacyResponse.data;
        const transformedTranscript: TwilioTranscriptDetail = {
          sid: legacy.transcript_sid,
          status: legacy.status,
          date_created: legacy.date_created,
          date_updated: legacy.date_updated || legacy.date_created,
          duration: legacy.duration,
          language_code: legacy.language_code,
          sentences: legacy.sentences ? legacy.sentences.map(s => ({
            text: s.transcript,
            speaker: parseInt(s.speaker) || 0,
            start_time: s.start_time,
            end_time: s.end_time,
            confidence: s.confidence
          })) : []
        };
        
        setTranscript(transformedTranscript);
        
      } catch (err) {
        setError('Failed to load transcript details');
        console.error('Error fetching transcript:', err);
      } finally {
        setLoading(false);
      }
    };

    if (transcriptSid) {
      fetchTranscript();
    }
  }, [transcriptSid]);

  if (loading) return <div className="p-4">Loading transcript details...</div>;
  if (error) return <div className="p-4 text-red-500">{error}</div>;
  if (!transcript) return <div className="p-4">No transcript found</div>;

  // Format duration from seconds to minutes:seconds
  const formatDuration = (seconds: number) => {
    if (!seconds) return '0:00';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  // Format timestamp from seconds to minutes:seconds
  const formatTimestamp = (seconds: number) => {
    if (seconds === undefined || seconds === null) return '0:00';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  // Create full text from sentences
  const fullText = transcript.sentences.map(s => s.text).join(' ');

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold mb-4">Transcript Details</h2>
      
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <p className="text-gray-500">Transcript ID</p>
            <p className="font-medium">{transcript.sid}</p>
          </div>
          <div>
            <p className="text-gray-500">Status</p>
            <p className="font-medium">
              <span className={`px-2 py-1 rounded-full text-xs ${
                transcript.status === 'completed' ? 'bg-green-100 text-green-800' : 
                transcript.status === 'failed' ? 'bg-red-100 text-red-800' : 
                'bg-yellow-100 text-yellow-800'
              }`}>
                {transcript.status}
              </span>
            </p>
          </div>
          <div>
            <p className="text-gray-500">Created</p>
            <p className="font-medium">{new Date(transcript.date_created).toLocaleString()}</p>
          </div>
          <div>
            <p className="text-gray-500">Duration</p>
            <p className="font-medium">{formatDuration(transcript.duration)}</p>
          </div>
          <div>
            <p className="text-gray-500">Language</p>
            <p className="font-medium">{transcript.language_code}</p>
          </div>
          <div>
            <p className="text-gray-500">Sentences</p>
            <p className="font-medium">{transcript.sentences.length} sentences</p>
          </div>
        </div>
      </div>

      {fullText && (
        <div className="bg-white shadow rounded-lg p-6 mb-6">
          <h3 className="text-xl font-semibold mb-4">Full Transcript</h3>
          <div className="bg-gray-50 p-4 rounded">
            <p className="whitespace-pre-wrap">{fullText}</p>
          </div>
        </div>
      )}

      {transcript.sentences && transcript.sentences.length > 0 && (
        <div className="bg-white shadow rounded-lg p-6">
          <h3 className="text-xl font-semibold mb-4">Sentences</h3>
          <div className="space-y-4">
            {transcript.sentences.map((sentence, index) => (
              <div key={index} className="border-b pb-3 last:border-b-0">
                <div className="flex justify-between mb-1">
                  <span className="font-medium text-blue-600">
                    Speaker {sentence.speaker}
                  </span>
                  <span className="text-gray-500 text-sm">
                    {formatTimestamp(sentence.start_time)} - {formatTimestamp(sentence.end_time)}
                  </span>
                </div>
                <p>{sentence.text}</p>
                <div className="mt-1 text-xs text-gray-500">
                  Confidence: {Math.round(sentence.confidence * 100)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}; 