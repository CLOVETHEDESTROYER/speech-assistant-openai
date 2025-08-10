#!/usr/bin/env python3
"""
Migration script to transfer data from SQLite to PostgreSQL
Run this script to migrate your existing SQLite data to PostgreSQL
"""

from app.models import Base, User, CustomScenario, Conversation, StoredTwilioTranscript
from app.db import test_database_connection
import os
import sys
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_postgresql_tables(postgres_engine):
    """Create all tables in PostgreSQL"""
    try:
        Base.metadata.create_all(bind=postgres_engine)
        logger.info("PostgreSQL tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to create PostgreSQL tables: {str(e)}")
        return False


def migrate_users(sqlite_session, postgres_session):
    """Migrate users from SQLite to PostgreSQL"""
    try:
        users = sqlite_session.query(User).all()
        logger.info(f"Found {len(users)} users to migrate")

        for user in users:
            # Check if user already exists in PostgreSQL
            existing_user = postgres_session.query(
                User).filter(User.email == user.email).first()
            if not existing_user:
                new_user = User(
                    email=user.email,
                    hashed_password=user.hashed_password,
                    is_active=user.is_active,
                    is_admin=user.is_admin
                    # Note: subscription_status is in UsageLimits table, not User table
                )
                postgres_session.add(new_user)
                logger.info(f"Added user: {user.email}")
            else:
                logger.info(f"User already exists: {user.email}")

        postgres_session.commit()
        logger.info("Users migration completed successfully")
        return True
    except Exception as e:
        postgres_session.rollback()
        logger.error(f"Failed to migrate users: {str(e)}")
        return False


def migrate_custom_scenarios(sqlite_session, postgres_session):
    """Migrate custom scenarios from SQLite to PostgreSQL"""
    try:
        scenarios = sqlite_session.query(CustomScenario).all()
        logger.info(f"Found {len(scenarios)} custom scenarios to migrate")

        for scenario in scenarios:
            # Check if scenario already exists
            existing_scenario = postgres_session.query(CustomScenario).filter(
                CustomScenario.scenario_id == scenario.scenario_id
            ).first()

            if not existing_scenario:
                new_scenario = CustomScenario(
                    scenario_id=scenario.scenario_id,
                    user_id=scenario.user_id,
                    persona=scenario.persona,
                    prompt=scenario.prompt,
                    voice_type=scenario.voice_type,
                    temperature=scenario.temperature,
                    created_at=scenario.created_at
                    # Note: updated_at field doesn't exist in the model
                )
                postgres_session.add(new_scenario)
                logger.info(f"Added scenario: {scenario.name}")
            else:
                logger.info(f"Scenario already exists: {scenario.name}")

        postgres_session.commit()
        logger.info("Custom scenarios migration completed successfully")
        return True
    except Exception as e:
        postgres_session.rollback()
        logger.error(f"Failed to migrate custom scenarios: {str(e)}")
        return False


def migrate_conversations(sqlite_session, postgres_session):
    """Migrate conversations from SQLite to PostgreSQL"""
    try:
        conversations = sqlite_session.query(Conversation).all()
        logger.info(f"Found {len(conversations)} conversations to migrate")

        for conv in conversations:
            # Check if conversation already exists
            existing_conv = postgres_session.query(Conversation).filter(
                Conversation.id == conv.id
            ).first()

            if not existing_conv:
                new_conv = Conversation(
                    id=conv.id,
                    user_id=conv.user_id,
                    scenario=conv.scenario,  # Note: field name is 'scenario', not 'scenario_id'
                    phone_number=conv.phone_number,
                    status=conv.status,
                    call_sid=conv.call_sid,
                    recording_sid=conv.recording_sid,
                    transcript=conv.transcript,
                    created_at=conv.created_at,
                    transcript_sid=conv.transcript_sid,
                    duration_limit=conv.duration_limit
                    # Note: 'direction' field doesn't exist in the model
                )
                postgres_session.add(new_conv)
                logger.info(f"Added conversation: {conv.id}")
            else:
                logger.info(f"Conversation already exists: {conv.id}")

        postgres_session.commit()
        logger.info("Conversations migration completed successfully")
        return True
    except Exception as e:
        postgres_session.rollback()
        logger.error(f"Failed to migrate conversations: {str(e)}")
        return False


def migrate_transcripts(sqlite_session, postgres_session):
    """Migrate stored transcripts from SQLite to PostgreSQL"""
    try:
        transcripts = sqlite_session.query(StoredTwilioTranscript).all()
        logger.info(f"Found {len(transcripts)} transcripts to migrate")

        for transcript in transcripts:
            # Check if transcript already exists
            existing_transcript = postgres_session.query(StoredTwilioTranscript).filter(
                StoredTwilioTranscript.id == transcript.id
            ).first()

            if not existing_transcript:
                new_transcript = StoredTwilioTranscript(
                    id=transcript.id,
                    user_id=transcript.user_id,
                    transcript_sid=transcript.transcript_sid,
                    status=transcript.status,
                    date_created=transcript.date_created,
                    date_updated=transcript.date_updated,
                    duration=transcript.duration,
                    language_code=transcript.language_code,
                    sentences=transcript.sentences,
                    call_sid=transcript.call_sid,
                    scenario_name=transcript.scenario_name,
                    call_direction=transcript.call_direction,
                    phone_number=transcript.phone_number,
                    created_at=transcript.created_at
                    # Note: 'conversation_id' and 'confidence_score' fields don't exist in the model
                )
                postgres_session.add(new_transcript)
                logger.info(f"Added transcript: {transcript.id}")
            else:
                logger.info(f"Transcript already exists: {transcript.id}")

        postgres_session.commit()
        logger.info("Transcripts migration completed successfully")
        return True
    except Exception as e:
        postgres_session.rollback()
        logger.error(f"Failed to migrate transcripts: {str(e)}")
        return False


def main():
    """Main migration function"""
    logger.info("Starting migration from SQLite to PostgreSQL...")

    # Check if PostgreSQL connection is available
    if not test_database_connection():
        logger.error(
            "Cannot connect to PostgreSQL. Please check your configuration.")
        return False

    # Set up database connections
    sqlite_url = "sqlite:///./sql_app.db"
    postgres_url = os.getenv(
        "DATABASE_URL", "postgresql://speech_user:speech_password@localhost:5432/speech_assistant")

    try:
        # Create SQLite engine
        sqlite_engine = create_engine(sqlite_url, connect_args={
                                      "check_same_thread": False})
        sqlite_session = sessionmaker(bind=sqlite_engine)()

        # Create PostgreSQL engine
        postgres_engine = create_engine(postgres_url)
        postgres_session = sessionmaker(bind=postgres_engine)()

        logger.info("Database connections established successfully")

        # Create tables in PostgreSQL
        if not create_postgresql_tables(postgres_engine):
            return False

        # Migrate data
        success = True
        success &= migrate_users(sqlite_session, postgres_session)
        success &= migrate_custom_scenarios(sqlite_session, postgres_session)
        success &= migrate_conversations(sqlite_session, postgres_session)
        success &= migrate_transcripts(sqlite_session, postgres_session)

        if success:
            logger.info("Migration completed successfully!")
            logger.info("You can now update your .env file to use PostgreSQL")
            logger.info(
                "DATABASE_URL=postgresql://speech_user:speech_password@localhost:5432/speech_assistant")
        else:
            logger.error("Migration failed. Please check the logs above.")
            return False

    except Exception as e:
        logger.error(f"Migration failed with error: {str(e)}")
        return False
    finally:
        # Close sessions
        if 'sqlite_session' in locals():
            sqlite_session.close()
        if 'postgres_session' in locals():
            postgres_session.close()
        if 'sqlite_engine' in locals():
            sqlite_engine.dispose()
        if 'postgres_engine' in locals():
            postgres_engine.dispose()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
