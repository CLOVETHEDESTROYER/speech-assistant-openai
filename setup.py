from setuptools import setup, find_packages

setup(
    name="speech-assistant",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "sqlalchemy",
        "pydantic",
        "python-jose",
        "passlib",
        "python-dotenv",
        "twilio",
        "openai",
        "websockets",
    ],
)
