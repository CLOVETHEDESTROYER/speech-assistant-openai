import pytest
from app.models import CustomScenario
from datetime import datetime


def test_create_custom_scenario(client, auth_headers, db_session):
    """Test creating a custom scenario."""
    scenario_data = {
        "persona": "Test persona with sufficient length for validation",
        "prompt": "Test prompt with sufficient length for validation",
        "voice_type": "aggressive_male",
        "temperature": 0.7
    }

    response = client.post(
        "/realtime/custom-scenario",
        json=scenario_data,
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert "scenario_id" in data
    assert data["message"] == "Custom scenario created successfully"

    # Verify database entry
    db_scenario = db_session.query(CustomScenario).filter(
        CustomScenario.scenario_id == data["scenario_id"]
    ).first()
    assert db_scenario is not None
    assert db_scenario.persona == scenario_data["persona"]
    assert db_scenario.prompt == scenario_data["prompt"]


def test_create_custom_scenario_invalid_voice(client, auth_headers):
    """Test creating a custom scenario with invalid voice type."""
    scenario_data = {
        "persona": "Test persona with sufficient length for validation",
        "prompt": "Test prompt with sufficient length for validation",
        "voice_type": "invalid_voice",
        "temperature": 0.7
    }

    response = client.post(
        "/realtime/custom-scenario",
        json=scenario_data,
        headers=auth_headers
    )

    assert response.status_code == 400
    assert "Voice type must be one of" in response.json()["detail"]


def test_get_custom_scenarios(client, auth_headers, db_session, test_user):
    """Test retrieving custom scenarios."""
    # Create test scenarios
    scenarios = [
        CustomScenario(
            scenario_id=f"test_scenario_{i}",
            user_id=test_user.id,
            persona=f"Test persona {i}",
            prompt=f"Test prompt {i}",
            voice_type="aggressive_male",
            temperature=0.7,
            created_at=datetime.utcnow()
        ) for i in range(3)
    ]

    for scenario in scenarios:
        db_session.add(scenario)
    db_session.commit()

    response = client.get("/realtime/custom-scenarios", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(s["voice_type"] == "aggressive_male" for s in data)


def test_update_custom_scenario(client, auth_headers, db_session, test_user):
    """Test updating a custom scenario."""
    # Create test scenario
    scenario = CustomScenario(
        scenario_id="test_scenario",
        user_id=test_user.id,
        persona="Original persona",
        prompt="Original prompt",
        voice_type="aggressive_male",
        temperature=0.7,
        created_at=datetime.utcnow()
    )
    db_session.add(scenario)
    db_session.commit()

    update_data = {
        "persona": "Updated persona with sufficient length",
        "prompt": "Updated prompt with sufficient length",
        "voice_type": "concerned_female",
        "temperature": 0.8
    }

    response = client.put(
        f"/realtime/custom-scenario/{scenario.scenario_id}",
        json=update_data,
        headers=auth_headers
    )

    assert response.status_code == 200

    # Verify database update
    db_scenario = db_session.query(CustomScenario).filter(
        CustomScenario.scenario_id == scenario.scenario_id
    ).first()
    assert db_scenario.persona == update_data["persona"]
    assert db_scenario.voice_type == update_data["voice_type"]
    assert db_scenario.temperature == update_data["temperature"]


def test_delete_custom_scenario(client, auth_headers, db_session, test_user):
    """Test deleting a custom scenario."""
    # Create test scenario
    scenario = CustomScenario(
        scenario_id="test_scenario",
        user_id=test_user.id,
        persona="Test persona",
        prompt="Test prompt",
        voice_type="aggressive_male",
        temperature=0.7,
        created_at=datetime.utcnow()
    )
    db_session.add(scenario)
    db_session.commit()

    response = client.delete(
        f"/realtime/custom-scenario/{scenario.scenario_id}",
        headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Custom scenario deleted successfully"

    # Verify deletion
    db_scenario = db_session.query(CustomScenario).filter(
        CustomScenario.scenario_id == scenario.scenario_id
    ).first()
    assert db_scenario is None


def test_scenario_limit(client, auth_headers, db_session, test_user):
    """Test the limit of 20 custom scenarios per user."""
    # Create 20 scenarios
    for i in range(20):
        scenario = CustomScenario(
            scenario_id=f"test_scenario_{i}",
            user_id=test_user.id,
            persona=f"Test persona {i}",
            prompt=f"Test prompt {i}",
            voice_type="aggressive_male",
            temperature=0.7,
            created_at=datetime.utcnow()
        )
        db_session.add(scenario)
    db_session.commit()

    # Try to create one more
    scenario_data = {
        "persona": "Test persona with sufficient length for validation",
        "prompt": "Test prompt with sufficient length for validation",
        "voice_type": "aggressive_male",
        "temperature": 0.7
    }

    response = client.post(
        "/realtime/custom-scenario",
        json=scenario_data,
        headers=auth_headers
    )

    assert response.status_code == 400
    assert "maximum limit of 20 custom scenarios" in response.json()["detail"]
