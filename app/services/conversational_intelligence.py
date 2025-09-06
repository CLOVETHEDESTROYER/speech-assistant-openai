import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json
import re
from app.services.twilio_intelligence import TwilioIntelligenceService
from app.services.twilio_client import get_twilio_client
from app import config

logger = logging.getLogger(__name__)


class ConversationalIntelligenceService:
    """
    Enhanced service for conversational intelligence analysis including
    sentiment analysis, topic extraction, and conversation insights.
    """
    
    def __init__(self):
        """Initialize the Conversational Intelligence Service."""
        self.twilio_intelligence = TwilioIntelligenceService()
        self.twilio_client = get_twilio_client()
    
    async def analyze_conversation(
        self, 
        transcript_sid: str,
        include_sentiment: bool = True,
        include_topics: bool = True,
        include_insights: bool = True
    ) -> Dict[str, Any]:
        """
        Perform comprehensive analysis of a conversation transcript.
        
        Args:
            transcript_sid: The SID of the transcript to analyze
            include_sentiment: Whether to include sentiment analysis
            include_topics: Whether to include topic extraction
            include_insights: Whether to include conversation insights
            
        Returns:
            Dict containing analysis results
        """
        try:
            logger.info(f"Starting conversation analysis for transcript {transcript_sid}")
            
            # Get transcript data
            transcript_data = await self._get_transcript_data(transcript_sid)
            if not transcript_data:
                return {"error": "Failed to retrieve transcript data"}
            
            analysis_result = {
                "transcript_sid": transcript_sid,
                "analysis_timestamp": datetime.utcnow().isoformat(),
                "basic_info": {
                    "duration": transcript_data.get("duration", 0),
                    "language_code": transcript_data.get("language_code", "en-US"),
                    "sentence_count": len(transcript_data.get("sentences", []))
                }
            }
            
            # Perform sentiment analysis
            if include_sentiment:
                sentiment_analysis = await self._analyze_sentiment(transcript_data["sentences"])
                analysis_result["sentiment"] = sentiment_analysis
            
            # Extract topics
            if include_topics:
                topics = await self._extract_topics(transcript_data["sentences"])
                analysis_result["topics"] = topics
            
            # Generate conversation insights
            if include_insights:
                insights = await self._generate_insights(transcript_data["sentences"])
                analysis_result["insights"] = insights
            
            logger.info(f"Completed conversation analysis for transcript {transcript_sid}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing conversation {transcript_sid}: {str(e)}")
            return {"error": f"Analysis failed: {str(e)}"}
    
    async def _get_transcript_data(self, transcript_sid: str) -> Optional[Dict[str, Any]]:
        """Get transcript data from Twilio Intelligence API."""
        try:
            # Get transcript
            transcript = self.twilio_client.intelligence.v2.transcripts(transcript_sid).fetch()
            
            # Get sentences
            sentences = self.twilio_client.intelligence.v2.transcripts(transcript_sid).sentences.list()
            
            # Format sentences
            formatted_sentences = []
            for sentence in sentences:
                formatted_sentences.append({
                    "text": getattr(sentence, "text", ""),
                    "speaker": getattr(sentence, "speaker", 0),
                    "start_time": getattr(sentence, "start_time", 0),
                    "end_time": getattr(sentence, "end_time", 0),
                    "confidence": getattr(sentence, "confidence", 0)
                })
            
            return {
                "sid": transcript.sid,
                "status": transcript.status,
                "duration": transcript.duration,
                "language_code": transcript.language_code,
                "sentences": formatted_sentences
            }
            
        except Exception as e:
            logger.error(f"Error getting transcript data for {transcript_sid}: {str(e)}")
            return None
    
    async def _analyze_sentiment(self, sentences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze sentiment of conversation sentences.
        This is a basic implementation - in production, you'd use a proper NLP service.
        """
        try:
            # Basic sentiment analysis using keyword matching
            positive_keywords = [
                "good", "great", "excellent", "amazing", "wonderful", "fantastic",
                "love", "like", "happy", "pleased", "satisfied", "perfect"
            ]
            negative_keywords = [
                "bad", "terrible", "awful", "horrible", "hate", "dislike",
                "angry", "frustrated", "disappointed", "upset", "annoyed"
            ]
            
            positive_count = 0
            negative_count = 0
            neutral_count = 0
            total_confidence = 0
            
            for sentence in sentences:
                text = sentence.get("text", "").lower()
                confidence = sentence.get("confidence", 0)
                total_confidence += confidence
                
                # Check for positive sentiment
                if any(keyword in text for keyword in positive_keywords):
                    positive_count += 1
                # Check for negative sentiment
                elif any(keyword in text for keyword in negative_keywords):
                    negative_count += 1
                else:
                    neutral_count += 1
            
            total_sentences = len(sentences)
            avg_confidence = total_confidence / total_sentences if total_sentences > 0 else 0
            
            # Determine overall sentiment
            if positive_count > negative_count:
                overall_sentiment = "positive"
            elif negative_count > positive_count:
                overall_sentiment = "negative"
            else:
                overall_sentiment = "neutral"
            
            return {
                "overall_sentiment": overall_sentiment,
                "sentiment_scores": {
                    "positive": positive_count,
                    "negative": negative_count,
                    "neutral": neutral_count
                },
                "sentiment_percentages": {
                    "positive": round((positive_count / total_sentences) * 100, 2) if total_sentences > 0 else 0,
                    "negative": round((negative_count / total_sentences) * 100, 2) if total_sentences > 0 else 0,
                    "neutral": round((neutral_count / total_sentences) * 100, 2) if total_sentences > 0 else 0
                },
                "average_confidence": round(avg_confidence, 2)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {str(e)}")
            return {"error": f"Sentiment analysis failed: {str(e)}"}
    
    async def _extract_topics(self, sentences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract topics from conversation sentences.
        This is a basic implementation - in production, you'd use a proper NLP service.
        """
        try:
            # Common business topics
            topic_keywords = {
                "appointment": ["appointment", "schedule", "booking", "meeting", "calendar"],
                "billing": ["bill", "payment", "charge", "cost", "price", "money"],
                "support": ["help", "support", "issue", "problem", "trouble", "fix"],
                "product": ["product", "service", "feature", "functionality"],
                "complaint": ["complaint", "complain", "unhappy", "dissatisfied"],
                "compliment": ["compliment", "praise", "thank", "appreciate"],
                "cancellation": ["cancel", "cancellation", "refund", "return"]
            }
            
            topic_counts = {topic: 0 for topic in topic_keywords.keys()}
            topic_sentences = {topic: [] for topic in topic_keywords.keys()}
            
            for sentence in sentences:
                text = sentence.get("text", "").lower()
                for topic, keywords in topic_keywords.items():
                    if any(keyword in text for keyword in keywords):
                        topic_counts[topic] += 1
                        topic_sentences[topic].append(sentence.get("text", ""))
            
            # Get top topics
            sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
            top_topics = [topic for topic, count in sorted_topics if count > 0]
            
            return {
                "detected_topics": top_topics,
                "topic_counts": topic_counts,
                "topic_examples": {
                    topic: sentences[:3] for topic, sentences in topic_sentences.items() 
                    if sentences
                }
            }
            
        except Exception as e:
            logger.error(f"Error extracting topics: {str(e)}")
            return {"error": f"Topic extraction failed: {str(e)}"}
    
    async def _generate_insights(self, sentences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate conversation insights and metrics.
        """
        try:
            total_duration = 0
            speaker_talk_time = {}
            speaker_sentence_count = {}
            high_confidence_sentences = 0
            low_confidence_sentences = 0
            
            for sentence in sentences:
                speaker = sentence.get("speaker", 0)
                start_time = sentence.get("start_time", 0)
                end_time = sentence.get("end_time", 0)
                confidence = sentence.get("confidence", 0)
                
                # Calculate talk time
                duration = end_time - start_time
                total_duration += duration
                
                if speaker not in speaker_talk_time:
                    speaker_talk_time[speaker] = 0
                    speaker_sentence_count[speaker] = 0
                
                speaker_talk_time[speaker] += duration
                speaker_sentence_count[speaker] += 1
                
                # Track confidence levels
                if confidence > 0.8:
                    high_confidence_sentences += 1
                elif confidence < 0.5:
                    low_confidence_sentences += 1
            
            # Calculate metrics
            total_sentences = len(sentences)
            avg_confidence = sum(s.get("confidence", 0) for s in sentences) / total_sentences if total_sentences > 0 else 0
            
            # Determine primary speaker
            primary_speaker = max(speaker_talk_time.items(), key=lambda x: x[1])[0] if speaker_talk_time else 0
            
            # Calculate talk time percentages
            speaker_percentages = {}
            for speaker, talk_time in speaker_talk_time.items():
                speaker_percentages[speaker] = round((talk_time / total_duration) * 100, 2) if total_duration > 0 else 0
            
            return {
                "conversation_metrics": {
                    "total_duration_seconds": round(total_duration, 2),
                    "total_sentences": total_sentences,
                    "average_confidence": round(avg_confidence, 2),
                    "high_confidence_percentage": round((high_confidence_sentences / total_sentences) * 100, 2) if total_sentences > 0 else 0,
                    "low_confidence_percentage": round((low_confidence_sentences / total_sentences) * 100, 2) if total_sentences > 0 else 0
                },
                "speaker_analysis": {
                    "primary_speaker": primary_speaker,
                    "speaker_talk_time": speaker_talk_time,
                    "speaker_percentages": speaker_percentages,
                    "speaker_sentence_counts": speaker_sentence_count
                },
                "conversation_quality": {
                    "transcription_quality": "high" if avg_confidence > 0.8 else "medium" if avg_confidence > 0.6 else "low",
                    "conversation_balance": "balanced" if len(speaker_talk_time) > 1 else "one-sided"
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            return {"error": f"Insight generation failed: {str(e)}"}
    
    async def get_conversation_summary(self, transcript_sid: str) -> Dict[str, Any]:
        """
        Get a high-level summary of the conversation.
        """
        try:
            analysis = await self.analyze_conversation(transcript_sid)
            
            if "error" in analysis:
                return analysis
            
            # Create summary
            summary = {
                "transcript_sid": transcript_sid,
                "summary_timestamp": datetime.utcnow().isoformat(),
                "duration_minutes": round(analysis["basic_info"]["duration"] / 60, 2),
                "sentence_count": analysis["basic_info"]["sentence_count"],
                "language": analysis["basic_info"]["language_code"]
            }
            
            # Add sentiment summary
            if "sentiment" in analysis:
                summary["sentiment"] = analysis["sentiment"]["overall_sentiment"]
                summary["sentiment_confidence"] = analysis["sentiment"]["average_confidence"]
            
            # Add topic summary
            if "topics" in analysis and "detected_topics" in analysis["topics"]:
                summary["main_topics"] = analysis["topics"]["detected_topics"][:3]  # Top 3 topics
            
            # Add quality summary
            if "insights" in analysis and "conversation_quality" in analysis["insights"]:
                summary["transcription_quality"] = analysis["insights"]["conversation_quality"]["transcription_quality"]
                summary["conversation_balance"] = analysis["insights"]["conversation_quality"]["conversation_balance"]
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating conversation summary for {transcript_sid}: {str(e)}")
            return {"error": f"Summary generation failed: {str(e)}"}
    
    async def batch_analyze_conversations(self, transcript_sids: List[str]) -> Dict[str, Any]:
        """
        Analyze multiple conversations in batch.
        """
        try:
            results = {}
            successful_analyses = 0
            failed_analyses = 0
            
            for transcript_sid in transcript_sids:
                try:
                    analysis = await self.analyze_conversation(transcript_sid)
                    results[transcript_sid] = analysis
                    
                    if "error" not in analysis:
                        successful_analyses += 1
                    else:
                        failed_analyses += 1
                        
                except Exception as e:
                    logger.error(f"Error analyzing transcript {transcript_sid}: {str(e)}")
                    results[transcript_sid] = {"error": str(e)}
                    failed_analyses += 1
            
            return {
                "batch_analysis_timestamp": datetime.utcnow().isoformat(),
                "total_transcripts": len(transcript_sids),
                "successful_analyses": successful_analyses,
                "failed_analyses": failed_analyses,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error in batch analysis: {str(e)}")
            return {"error": f"Batch analysis failed: {str(e)}"}
