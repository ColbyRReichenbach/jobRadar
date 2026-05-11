"""Seed the database with realistic job postings for demo/testing."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.env import load_app_env

load_app_env()

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.models import Base, Application, Contact, EmailEvent
from datetime import datetime, timezone, timedelta
import uuid


SEED_JOBS = [
    {
        "company": "Stripe",
        "role_title": "Frontend Engineer",
        "location": "San Francisco, CA",
        "salary": "$140k - $180k",
        "status": "interviewing",
        "source": "linkedin",
        "job_url": "https://stripe.com/jobs/frontend-engineer",
        "description_text": "Build intuitive, accessible, and highly performant user interfaces for Stripe's payment products. 4+ years React/TypeScript experience required.",
        "notes": "Recruiter screen done. Technical screen next week — brush up on React patterns and web accessibility.",
        "logo_url": "https://logo.clearbit.com/stripe.com",
        "days_ago": 7,
        "contacts": [
            {"name": "Sarah Jenkins", "title": "Technical Recruiter", "email": "sarah@stripe.com"},
        ],
    },
    {
        "company": "Vercel",
        "role_title": "Software Engineer",
        "location": "Remote",
        "salary": "$130k - $160k",
        "status": "applied",
        "source": "company_site",
        "job_url": "https://vercel.com/careers/software-engineer",
        "description_text": "Join Vercel to work on Next.js and its surrounding ecosystem. Build and maintain core framework features.",
        "notes": "Applied via careers page. Take-home assessment due in 48 hours.",
        "logo_url": "https://logo.clearbit.com/vercel.com",
        "days_ago": 3,
    },
    {
        "company": "Linear",
        "role_title": "Product Engineer",
        "location": "Remote",
        "status": "saved",
        "source": "linkedin",
        "job_url": "https://linear.app/careers/product-engineer",
        "logo_url": "https://logo.clearbit.com/linear.app",
        "days_ago": 1,
    },
    {
        "company": "Airbnb",
        "role_title": "Software Engineer, Guest Experience",
        "location": "Seattle, WA",
        "status": "rejected",
        "source": "indeed",
        "job_url": "https://airbnb.com/careers/software-engineer",
        "logo_url": "https://logo.clearbit.com/airbnb.com",
        "days_ago": 21,
    },
    {
        "company": "Notion",
        "role_title": "Fullstack Engineer",
        "location": "New York, NY",
        "salary": "$150k - $190k",
        "status": "offer",
        "source": "glassdoor",
        "job_url": "https://notion.so/careers/fullstack-engineer",
        "logo_url": "https://logo.clearbit.com/notion.so",
        "days_ago": 16,
    },
    {
        "company": "OpenAI",
        "role_title": "Frontend Engineer",
        "location": "San Francisco, CA",
        "status": "interviewing",
        "source": "linkedin",
        "job_url": "https://openai.com/careers/frontend-engineer",
        "logo_url": "https://logo.clearbit.com/openai.com",
        "days_ago": 6,
        "contacts": [
            {"name": "Alex Recruiter", "title": "Talent Partner", "email": "alex.r@openai.com"},
        ],
    },
    {
        "company": "Figma",
        "role_title": "Product Designer",
        "location": "Remote",
        "salary": "$120k - $160k",
        "status": "applied",
        "source": "company_site",
        "job_url": "https://figma.com/careers/product-designer",
        "logo_url": "https://logo.clearbit.com/figma.com",
        "days_ago": 2,
    },
    {
        "company": "Google",
        "role_title": "Senior Software Engineer",
        "location": "Mountain View, CA",
        "salary": "$180k - $250k",
        "status": "rejected",
        "source": "linkedin",
        "job_url": "https://google.com/careers/senior-swe",
        "logo_url": "https://logo.clearbit.com/google.com",
        "days_ago": 52,
    },
    {
        "company": "Apple",
        "role_title": "Frontend Developer",
        "location": "Cupertino, CA",
        "status": "saved",
        "source": "indeed",
        "job_url": "https://apple.com/jobs/frontend-dev",
        "logo_url": "https://logo.clearbit.com/apple.com",
        "days_ago": 0,
    },
    {
        "company": "Meta",
        "role_title": "Product Engineer",
        "location": "Menlo Park, CA",
        "salary": "$160k - $210k",
        "status": "interviewing",
        "source": "glassdoor",
        "job_url": "https://meta.com/careers/product-engineer",
        "logo_url": "https://logo.clearbit.com/meta.com",
        "days_ago": 8,
        "contacts": [
            {"name": "David Chen", "title": "Engineering Manager", "email": "dchen@meta.com"},
        ],
    },
    {
        "company": "Amazon",
        "role_title": "Frontend Engineer",
        "location": "Seattle, WA",
        "status": "saved",
        "source": "linkedin",
        "job_url": "https://amazon.jobs/frontend-engineer",
        "logo_url": "https://logo.clearbit.com/amazon.com",
        "days_ago": 0,
    },
    {
        "company": "Shopify",
        "role_title": "Senior Frontend Developer",
        "location": "Remote",
        "salary": "$135k - $175k",
        "status": "applied",
        "source": "linkedin",
        "job_url": "https://shopify.com/careers/senior-frontend",
        "description_text": "Build merchant-facing experiences using React and Polaris. Remote-first culture.",
        "logo_url": "https://logo.clearbit.com/shopify.com",
        "days_ago": 4,
    },
    {
        "company": "Datadog",
        "role_title": "Software Engineer, Frontend",
        "location": "New York, NY",
        "salary": "$145k - $185k",
        "status": "applied",
        "source": "glassdoor",
        "job_url": "https://datadog.com/careers/frontend-swe",
        "logo_url": "https://logo.clearbit.com/datadoghq.com",
        "days_ago": 5,
    },
    {
        "company": "Coinbase",
        "role_title": "Frontend Engineer",
        "location": "Remote",
        "salary": "$155k - $195k",
        "status": "saved",
        "source": "company_site",
        "job_url": "https://coinbase.com/careers/frontend",
        "logo_url": "https://logo.clearbit.com/coinbase.com",
        "days_ago": 1,
    },
    {
        "company": "Slack",
        "role_title": "UI Developer",
        "location": "Remote",
        "status": "saved",
        "source": "indeed",
        "job_url": "https://slack.com/careers/ui-developer",
        "logo_url": "https://logo.clearbit.com/slack.com",
        "days_ago": 7,
    },
]

SEED_EMAILS = [
    {
        "job_company": "Stripe",
        "sender": "Sarah Jenkins",
        "sender_email": "sarah@stripe.com",
        "subject": "Stripe Frontend Engineer - Next Steps",
        "snippet": "We loved your background and would like to invite you to a technical interview...",
        "body": "Hi there,\n\nThank you for taking the time to speak with our team last week. We loved your background and the insights you shared about your previous projects.\n\nWe would like to invite you to a technical interview with our engineering team. This will be a 60-minute session focusing on React and system design.\n\nPlease let me know your availability for next week.\n\nBest,\nSarah Jenkins\nTechnical Recruiter, Stripe",
        "classification": "interview",
        "email_type": "decision",
        "thread_id": "t1",
        "days_ago": 0,
        "read": False,
    },
    {
        "job_company": "Airbnb",
        "sender": "Airbnb Recruiting",
        "sender_email": "careers@airbnb.com",
        "subject": "Update on your application",
        "snippet": "After careful consideration, we have decided to move forward with other candidates...",
        "body": "Hi,\n\nThank you for taking the time to apply for the Software Engineer, Guest Experience role at Airbnb.\n\nWe received many strong applications for this position. After careful consideration, we have decided to move forward with other candidates whose experience more closely matches our current needs.\n\nWe appreciate your interest in Airbnb and wish you the best in your job search.\n\nSincerely,\nThe Airbnb Recruiting Team",
        "classification": "rejection",
        "email_type": "decision",
        "thread_id": "t2",
        "days_ago": 2,
        "read": True,
    },
    {
        "job_company": "Vercel",
        "sender": "Vercel Careers",
        "sender_email": "recruiting@vercel.com",
        "subject": "Action Required: Complete your Vercel Application",
        "snippet": "Please complete the coding assessment linked below within the next 48 hours...",
        "body": "Hello,\n\nThanks for applying to Vercel! To proceed with your application for the Software Engineer role, please complete the coding assessment linked below.\n\nYou will have 48 hours to complete the assessment once you begin.\n\n[Link to Assessment]\n\nBest of luck,\nVercel Recruiting",
        "classification": "action_item",
        "email_type": "decision",
        "thread_id": "t3",
        "days_ago": 1,
        "read": False,
        "action_needed": True,
    },
    {
        "job_company": "OpenAI",
        "sender": "Alex Recruiter",
        "sender_email": "alex.r@openai.com",
        "subject": "Re: Frontend Engineer Role - Availability",
        "snippet": "Great, I have scheduled you for Tuesday at 2 PM PST.",
        "body": "Great, I have scheduled you for Tuesday at 2 PM PST. I'll send over the calendar invite shortly.\n\nLet me know if you need anything else to prepare.\n\nBest,\nAlex",
        "classification": "update",
        "email_type": "conversation",
        "thread_id": "t4",
        "days_ago": 1,
        "read": True,
    },
    {
        "job_company": "Meta",
        "sender": "David Chen",
        "sender_email": "dchen@meta.com",
        "subject": "Following up on our chat",
        "snippet": "Have you had a chance to review the materials I sent over?",
        "body": "Hi,\n\nJust following up on our chat from last week. Have you had a chance to review the materials I sent over regarding the Product Engineer role?\n\nLet me know if you have any questions.\n\nThanks,\nDavid",
        "classification": "update",
        "email_type": "conversation",
        "thread_id": "t5",
        "days_ago": 3,
        "read": True,
        "action_needed": True,
    },
]


async def seed():
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./apptrail.db")
    engine = create_async_engine(db_url, echo=False)

    # Create tables if they don't exist (for SQLite dev)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    app_map = {}  # company -> application id

    async with session_factory() as session:
        # Seed jobs
        for job in SEED_JOBS:
            app = Application(
                company=job["company"],
                role_title=job["role_title"],
                location=job.get("location"),
                salary=job.get("salary"),
                status=job["status"],
                source=job.get("source"),
                job_url=job.get("job_url"),
                description_text=job.get("description_text"),
                notes=job.get("notes"),
                logo_url=job.get("logo_url"),
                applied_at=now - timedelta(days=job.get("days_ago", 0)),
            )
            session.add(app)
            await session.flush()
            app_map[job["company"]] = app.id

            # Add contacts
            for c in job.get("contacts", []):
                contact = Contact(
                    application_id=app.id,
                    name=c["name"],
                    title=c["title"],
                    email=c["email"],
                    source="seed",
                )
                session.add(contact)

        # Seed emails
        for email in SEED_EMAILS:
            app_id = app_map.get(email["job_company"])
            event = EmailEvent(
                application_id=app_id,
                sender=email["sender"],
                sender_email=email["sender_email"],
                subject=email["subject"],
                snippet=email["snippet"],
                body=email["body"],
                classification=email["classification"],
                email_type=email["email_type"],
                thread_id=email["thread_id"],
                received_at=now - timedelta(days=email.get("days_ago", 0)),
                read=email.get("read", False),
                action_needed=email.get("action_needed", False),
                gmail_message_id=f"seed-{uuid.uuid4().hex[:12]}",
            )
            session.add(event)

        await session.commit()

    print(f"Seeded {len(SEED_JOBS)} jobs and {len(SEED_EMAILS)} emails.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
