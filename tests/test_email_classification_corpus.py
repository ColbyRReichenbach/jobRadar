import pytest


@pytest.mark.parametrize(
    ("subject", "body", "sender", "sender_email", "expected_classification"),
    [
        (
            "Your application update",
            "We have decided not to move forward with your candidacy and will be pursuing other candidates.",
            "Greenhouse",
            "noreply@greenhouse.io",
            "rejection",
        ),
        (
            "Decision on your candidacy",
            "At this time, you have not been accepted for the Software Engineer position.",
            "Talent Team",
            "careers@company.com",
            "rejection",
        ),
        (
            "Schedule your final interview",
            "Please use the Calendly link below to select a time for your final interview loop.",
            "Jane Doe",
            "jane.doe@company.com",
            "interview_request",
        ),
        (
            "Complete your take-home assessment",
            "Please complete the coding challenge within the next 5 days.",
            "Hiring Team",
            "assessments@company.com",
            "action_item",
        ),
        (
            "Written offer for Senior Product Manager",
            "We are excited to extend an offer and share your compensation package.",
            "Alex Recruiter",
            "alex.recruiter@company.com",
            "offer",
        ),
        (
            "Application received",
            "Thank you for applying. We have received your application and it is under review.",
            "Workday",
            "noreply@myworkday.com",
            "job_update",
        ),
        (
            "Following up on our conversation",
            "Great speaking with you today. Would you be open to a quick chat this week about the backend role?",
            "Maya Patel",
            "maya.patel@agency.com",
            "conversation",
        ),
        (
            "Build failed for AppTrail",
            "One of your builds failed to leave the wheelhouse. View build logs.",
            "Railway",
            "hello@notify.railway.app",
            "not_relevant",
        ),
        (
            "Take control of your career in the AI age",
            "Our practical guide is coming soon. Subscribe for more career content.",
            "LinkedIn",
            "linkedin@em.linkedin.com",
            "not_relevant",
        ),
        (
            "Celebrate Excellence With Us April 17",
            "Join us for the Carolina Alumni Awards Gala and community event next month.",
            "Carolina Alumni",
            "community@alumni.unc.edu",
            "not_relevant",
        ),
        (
            "First-year standard .com pricing drops tomorrow",
            "Check out our domains page tomorrow for the new launch pricing.",
            "Vercel",
            "hello@vercel.com",
            "not_relevant",
        ),
        (
            "Application update",
            "Your application has progressed to the next stage. No action is needed right now.",
            "Talent Ops",
            "hiring@company.com",
            "job_update",
        ),
    ],
)
def test_fallback_classification_corpus(
    subject: str,
    body: str,
    sender: str,
    sender_email: str,
    expected_classification: str,
):
    from backend.services.email_classifier import _fallback_classify

    result = _fallback_classify(subject, body, sender_email, sender=sender)
    assert result["classification"] == expected_classification


@pytest.mark.parametrize(
    ("sender", "sender_email", "classification", "expected"),
    [
        ("Jane Doe", "jane.doe@company.com", "conversation", True),
        ("Alex Recruiter", "alex@recruitingfirm.com", "job_update", True),
        ("Talent Team", "talent@company.com", "job_update", False),
        ("GitHub", "noreply@github.com", "not_relevant", False),
        ("Railway", "hello@notify.railway.app", "not_relevant", False),
    ],
)
def test_network_contact_candidate_rules(sender: str, sender_email: str, classification: str, expected: bool):
    from backend.services.email_classifier import should_create_network_contact

    assert should_create_network_contact(sender, sender_email, classification) is expected


def test_prefilter_blocks_promotional_company_noise():
    from backend.services.email_filter import is_obvious_noise_email, should_classify

    email = {
        "sender_email": "newsletter@company.com",
        "sender_name": "Company News",
        "subject": "Join our product webinar next week",
        "body": "Learn about our latest release notes and roadmap.",
    }

    assert is_obvious_noise_email(email) is True
    assert should_classify(email, {"company.com"}) is False


def test_prefilter_keeps_recruiter_follow_up():
    from backend.services.email_filter import should_classify

    email = {
        "sender_email": "jane.doe@staffingfirm.com",
        "sender_name": "Jane Doe",
        "subject": "Following up on the Staff Engineer role",
        "body": "Would you have time this week to discuss the position?",
    }

    assert should_classify(email, set()) is True
