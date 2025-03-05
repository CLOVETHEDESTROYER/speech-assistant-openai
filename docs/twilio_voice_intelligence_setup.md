# Setting Up Twilio Voice Intelligence for PII Redaction

This guide will help you set up Twilio Voice Intelligence API to transcribe your call recordings with automatic PII (Personally Identifiable Information) redaction.

## Prerequisites

- A Twilio account with Voice capabilities
- An existing Twilio Voice Intelligence API service or ability to create one
- API access to your Twilio account (Account SID and Auth Token)

## Step 1: Create a Voice Intelligence Service

1. Log in to the [Twilio Console](https://www.twilio.com/console)
2. Navigate to Voice > Voice Intelligence > [Services](https://www.twilio.com/console/voice/intelligence/services)
3. Click "Create new Voice Intelligence Service"
4. Provide a friendly name for your service (e.g., "Call Transcription Service")
5. Select the features you want to enable:
   - Transcriptions (required)
   - PII Redaction (optional, but recommended for privacy)
   - Any other language operators you wish to enable (e.g., keywords, sentiment analysis)
6. Click "Create"
7. Note the "Service SID" that starts with "VI..." - you'll need this for your application

## Step 2: Configure Your Environment Variables

Add the following environment variables to your application:

```
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_VOICE_INTELLIGENCE_SID=your_voice_intelligence_sid
```

## Step 3: Install Required Dependencies

Make sure you have the latest Twilio Python SDK installed:

```bash
pip install twilio>=8.0.0
```

Add this to your requirements.txt:

```
twilio>=8.0.0
```

## Step 4: Test Your Integration

After implementing the code changes in your application, test the integration by:

1. Making a test call to your Twilio number
2. Checking that the recording is processed by Twilio Voice Intelligence
3. Verifying that the transcript is saved to your database
4. Confirming that PII has been properly redacted in the stored transcript

## Understanding PII Redaction

Twilio Voice Intelligence can redact various types of personally identifiable information, including:

- Names
- Phone numbers
- Email addresses
- Credit card numbers
- Social security numbers
- Addresses

For example, a transcript containing "My name is John Smith and my number is 555-123-4567"
might be redacted to "My name is [NAME] and my number is [PHONE_NUMBER]".

## Troubleshooting

- **Transcription not starting**: Verify that your Voice Intelligence SID is correct
- **PII not being redacted**: Ensure redaction is enabled both in your code and in the Voice Intelligence service settings
- **Errors during transcription**: Check your application logs and the Twilio Console for error messages

## Additional Resources

- [Twilio Voice Intelligence API Documentation](https://www.twilio.com/docs/voice/intelligence)
- [Voice Intelligence API Reference](https://www.twilio.com/docs/voice/intelligence/api/service-resource#pii-redaction)
- [Twilio Python SDK Documentation](https://www.twilio.com/docs/libraries/python)
