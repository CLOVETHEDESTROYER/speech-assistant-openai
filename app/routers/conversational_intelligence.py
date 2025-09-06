from fastapi import APIRouter, Depends, HTTPException, Body, Request, Query
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.utils.twilio_helpers import with_twilio_retry
from app.limiter import rate_limit
from app.models import User
from app.services.conversational_intelligence import ConversationalIntelligenceService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/conversational-intelligence/analyze/{transcript_sid}")
@rate_limit("20/minute")
@with_twilio_retry(max_retries=3)
async def analyze_conversation(
    transcript_sid: str,
    request: Request,
    include_sentiment: bool = Body(True, description="Include sentiment analysis"),
    include_topics: bool = Body(True, description="Include topic extraction"),
    include_insights: bool = Body(True, description="Include conversation insights"),
    current_user: User = Depends(get_current_user)
):
    """
    Perform comprehensive analysis of a conversation transcript including
    sentiment analysis, topic extraction, and conversation insights.
    """
    try:
        logger.info(f"Starting conversation analysis for transcript {transcript_sid}")
        
        intelligence_service = ConversationalIntelligenceService()
        
        analysis_result = await intelligence_service.analyze_conversation(
            transcript_sid=transcript_sid,
            include_sentiment=include_sentiment,
            include_topics=include_topics,
            include_insights=include_insights
        )
        
        if "error" in analysis_result:
            raise HTTPException(status_code=400, detail=analysis_result["error"])
        
        logger.info(f"Completed conversation analysis for transcript {transcript_sid}")
        return analysis_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing conversation {transcript_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/conversational-intelligence/summary/{transcript_sid}")
@rate_limit("30/minute")
@with_twilio_retry(max_retries=3)
async def get_conversation_summary(
    transcript_sid: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get a high-level summary of the conversation including key metrics,
    sentiment, topics, and conversation quality.
    """
    try:
        logger.info(f"Generating conversation summary for transcript {transcript_sid}")
        
        intelligence_service = ConversationalIntelligenceService()
        
        summary = await intelligence_service.get_conversation_summary(transcript_sid)
        
        if "error" in summary:
            raise HTTPException(status_code=400, detail=summary["error"])
        
        logger.info(f"Generated conversation summary for transcript {transcript_sid}")
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating summary for {transcript_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")


@router.post("/conversational-intelligence/batch-analyze")
@rate_limit("10/minute")
@with_twilio_retry(max_retries=3)
async def batch_analyze_conversations(
    request: Request,
    transcript_sids: List[str] = Body(..., description="List of transcript SIDs to analyze"),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze multiple conversations in batch for efficiency.
    """
    try:
        if len(transcript_sids) > 50:
            raise HTTPException(
                status_code=400, 
                detail="Maximum 50 transcripts allowed per batch analysis"
            )
        
        logger.info(f"Starting batch analysis for {len(transcript_sids)} transcripts")
        
        intelligence_service = ConversationalIntelligenceService()
        
        batch_result = await intelligence_service.batch_analyze_conversations(transcript_sids)
        
        if "error" in batch_result:
            raise HTTPException(status_code=400, detail=batch_result["error"])
        
        logger.info(f"Completed batch analysis for {len(transcript_sids)} transcripts")
        return batch_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch analysis failed: {str(e)}")


@router.get("/conversational-intelligence/sentiment/{transcript_sid}")
@rate_limit("30/minute")
@with_twilio_retry(max_retries=3)
async def get_sentiment_analysis(
    transcript_sid: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed sentiment analysis for a conversation transcript.
    """
    try:
        logger.info(f"Analyzing sentiment for transcript {transcript_sid}")
        
        intelligence_service = ConversationalIntelligenceService()
        
        analysis = await intelligence_service.analyze_conversation(
            transcript_sid=transcript_sid,
            include_sentiment=True,
            include_topics=False,
            include_insights=False
        )
        
        if "error" in analysis:
            raise HTTPException(status_code=400, detail=analysis["error"])
        
        if "sentiment" not in analysis:
            raise HTTPException(status_code=400, detail="Sentiment analysis not available")
        
        return {
            "transcript_sid": transcript_sid,
            "sentiment_analysis": analysis["sentiment"],
            "analysis_timestamp": analysis["analysis_timestamp"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing sentiment for {transcript_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sentiment analysis failed: {str(e)}")


@router.get("/conversational-intelligence/topics/{transcript_sid}")
@rate_limit("30/minute")
@with_twilio_retry(max_retries=3)
async def get_topic_analysis(
    transcript_sid: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get topic extraction analysis for a conversation transcript.
    """
    try:
        logger.info(f"Extracting topics for transcript {transcript_sid}")
        
        intelligence_service = ConversationalIntelligenceService()
        
        analysis = await intelligence_service.analyze_conversation(
            transcript_sid=transcript_sid,
            include_sentiment=False,
            include_topics=True,
            include_insights=False
        )
        
        if "error" in analysis:
            raise HTTPException(status_code=400, detail=analysis["error"])
        
        if "topics" not in analysis:
            raise HTTPException(status_code=400, detail="Topic analysis not available")
        
        return {
            "transcript_sid": transcript_sid,
            "topic_analysis": analysis["topics"],
            "analysis_timestamp": analysis["analysis_timestamp"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting topics for {transcript_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Topic analysis failed: {str(e)}")


@router.get("/conversational-intelligence/insights/{transcript_sid}")
@rate_limit("30/minute")
@with_twilio_retry(max_retries=3)
async def get_conversation_insights(
    transcript_sid: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed conversation insights and metrics for a transcript.
    """
    try:
        logger.info(f"Generating insights for transcript {transcript_sid}")
        
        intelligence_service = ConversationalIntelligenceService()
        
        analysis = await intelligence_service.analyze_conversation(
            transcript_sid=transcript_sid,
            include_sentiment=False,
            include_topics=False,
            include_insights=True
        )
        
        if "error" in analysis:
            raise HTTPException(status_code=400, detail=analysis["error"])
        
        if "insights" not in analysis:
            raise HTTPException(status_code=400, detail="Insights analysis not available")
        
        return {
            "transcript_sid": transcript_sid,
            "conversation_insights": analysis["insights"],
            "basic_info": analysis["basic_info"],
            "analysis_timestamp": analysis["analysis_timestamp"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating insights for {transcript_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Insights generation failed: {str(e)}")


@router.get("/conversational-intelligence/health")
async def health_check():
    """
    Health check endpoint for conversational intelligence service.
    """
    try:
        intelligence_service = ConversationalIntelligenceService()
        
        # Basic health check - try to initialize the service
        return {
            "status": "healthy",
            "service": "conversational_intelligence",
            "timestamp": "2024-01-01T00:00:00Z",
            "features": {
                "sentiment_analysis": True,
                "topic_extraction": True,
                "conversation_insights": True,
                "batch_analysis": True
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Service unhealthy: {str(e)}")


@router.get("/conversational-intelligence/analytics/dashboard")
@rate_limit("10/minute")
async def get_analytics_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    days: int = Query(7, description="Number of days to include in analytics")
):
    """
    Get analytics dashboard data for conversation intelligence.
    This is a placeholder for future implementation of aggregated analytics.
    """
    try:
        # This would typically query a database for aggregated analytics
        # For now, return a placeholder response
        
        return {
            "dashboard_timestamp": "2024-01-01T00:00:00Z",
            "period_days": days,
            "analytics": {
                "total_conversations": 0,
                "average_sentiment": "neutral",
                "top_topics": [],
                "conversation_quality_metrics": {
                    "high_quality_percentage": 0,
                    "medium_quality_percentage": 0,
                    "low_quality_percentage": 0
                },
                "sentiment_distribution": {
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0
                }
            },
            "message": "Analytics dashboard - implementation pending"
        }
        
    except Exception as e:
        logger.error(f"Error generating analytics dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Dashboard generation failed: {str(e)}")
