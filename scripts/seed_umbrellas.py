"""Seed role umbrella categories into the database."""
import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, RoleUmbrella

UMBRELLAS = [
    # Engineering
    {"name": "Software Engineer", "aliases": ["SWE", "Software Developer", "Programmer", "Application Developer", "Software Development Engineer"]},
    {"name": "Frontend Engineer", "aliases": ["Frontend Developer", "Front-End Engineer", "UI Engineer", "UI Developer", "Web Developer"]},
    {"name": "Backend Engineer", "aliases": ["Backend Developer", "Server-Side Developer", "API Developer"]},
    {"name": "Full Stack Engineer", "aliases": ["Full Stack Developer", "Fullstack Engineer", "Fullstack Developer"]},
    {"name": "Mobile Engineer", "aliases": ["Mobile Developer", "iOS Developer", "Android Developer", "iOS Engineer", "Android Engineer"]},
    {"name": "DevOps Engineer", "aliases": ["DevOps", "SRE", "Site Reliability Engineer", "Infrastructure Engineer", "Cloud Engineer"]},
    {"name": "Platform Engineer", "aliases": ["Platform Developer", "Infrastructure Developer"]},
    {"name": "ML Engineer", "aliases": ["Machine Learning Engineer", "AI Engineer", "Deep Learning Engineer", "ML/AI Engineer"]},
    {"name": "Data Engineer", "aliases": ["Data Pipeline Engineer", "ETL Developer", "Analytics Engineer"]},
    {"name": "Security Engineer", "aliases": ["InfoSec Engineer", "Cybersecurity Engineer", "Application Security Engineer", "Security Analyst"]},
    {"name": "QA Engineer", "aliases": ["Quality Assurance Engineer", "Test Engineer", "SDET", "QA Analyst", "Automation Engineer"]},
    {"name": "Embedded Systems Engineer", "aliases": ["Firmware Engineer", "Embedded Developer", "Hardware Engineer"]},
    {"name": "Game Developer", "aliases": ["Game Engineer", "Game Programmer", "Unity Developer", "Unreal Developer"]},
    # Data
    {"name": "Data Scientist", "aliases": ["Data Science", "ML Scientist", "Research Scientist", "Applied Scientist"]},
    {"name": "Data Analyst", "aliases": ["Business Analyst", "Quantitative Analyst", "BI Analyst"]},
    {"name": "Business Intelligence", "aliases": ["BI Developer", "BI Engineer", "Reporting Analyst"]},
    # Product
    {"name": "Product Manager", "aliases": ["PM", "Product Owner", "Product Lead"]},
    {"name": "Technical Program Manager", "aliases": ["TPM", "Program Manager", "Technical PM"]},
    {"name": "Product Analyst", "aliases": ["Product Data Analyst"]},
    # Design
    {"name": "UX Designer", "aliases": ["User Experience Designer", "UX/UI Designer", "Experience Designer"]},
    {"name": "UI Designer", "aliases": ["User Interface Designer", "Visual Designer", "Interaction Designer"]},
    {"name": "Product Designer", "aliases": ["Design Lead", "Digital Product Designer"]},
    {"name": "UX Researcher", "aliases": ["User Researcher", "Design Researcher"]},
    {"name": "Brand Designer", "aliases": ["Graphic Designer", "Creative Designer"]},
    {"name": "Motion Designer", "aliases": ["Animation Designer", "Motion Graphics Designer"]},
    # Marketing
    {"name": "Marketing Manager", "aliases": ["Marketing Lead", "Marketing Director"]},
    {"name": "Growth Marketing", "aliases": ["Growth Manager", "Growth Hacker", "Growth Lead"]},
    {"name": "Content Marketing", "aliases": ["Content Manager", "Content Strategist", "Content Writer"]},
    {"name": "SEO Specialist", "aliases": ["SEO Manager", "SEO Analyst", "Search Marketing"]},
    {"name": "Social Media Manager", "aliases": ["Social Media Specialist", "Community Manager"]},
    {"name": "Digital Marketing", "aliases": ["Online Marketing", "Performance Marketing", "Paid Media"]},
    # Sales
    {"name": "Account Executive", "aliases": ["AE", "Sales Executive", "Enterprise AE"]},
    {"name": "Sales Development Rep", "aliases": ["SDR", "BDR", "Business Development Rep"]},
    {"name": "Sales Engineer", "aliases": ["Solutions Engineer", "Pre-Sales Engineer", "Technical Sales"]},
    {"name": "Customer Success Manager", "aliases": ["CSM", "Client Success Manager", "Account Manager"]},
    {"name": "Solutions Architect", "aliases": ["Solution Architect", "Technical Architect", "Enterprise Architect"]},
    # Finance
    {"name": "Financial Analyst", "aliases": ["Finance Analyst", "Investment Analyst"]},
    {"name": "Accountant", "aliases": ["Staff Accountant", "Senior Accountant", "CPA"]},
    {"name": "FP&A", "aliases": ["Financial Planning", "FP&A Analyst", "Financial Planning Analyst"]},
    {"name": "Controller", "aliases": ["Financial Controller", "Accounting Manager"]},
    # Operations
    {"name": "Operations Manager", "aliases": ["Ops Manager", "Operations Lead"]},
    {"name": "Supply Chain", "aliases": ["Supply Chain Manager", "Logistics Manager", "Procurement"]},
    {"name": "Business Operations", "aliases": ["BizOps", "Strategic Operations"]},
    {"name": "Strategy & Operations", "aliases": ["StratOps", "Strategy Manager", "Chief of Staff"]},
    # HR
    {"name": "Recruiter", "aliases": ["Technical Recruiter", "Talent Acquisition Specialist", "Sourcer"]},
    {"name": "HR Business Partner", "aliases": ["HRBP", "People Partner"]},
    {"name": "People Operations", "aliases": ["PeopleOps", "HR Operations", "People Manager"]},
    # Legal
    {"name": "Corporate Counsel", "aliases": ["Legal Counsel", "Attorney", "Lawyer", "General Counsel"]},
    {"name": "Compliance", "aliases": ["Compliance Manager", "Compliance Officer", "Regulatory"]},
    {"name": "Paralegal", "aliases": ["Legal Assistant", "Legal Operations"]},
    # Executive
    {"name": "CTO", "aliases": ["Chief Technology Officer", "VP Technology"]},
    {"name": "VP Engineering", "aliases": ["VP of Engineering", "SVP Engineering"]},
    {"name": "Engineering Manager", "aliases": ["EM", "Software Engineering Manager", "Dev Manager"]},
    {"name": "Director of Engineering", "aliases": ["Engineering Director", "Senior Director Engineering"]},
    {"name": "Head of Product", "aliases": ["VP Product", "Chief Product Officer", "CPO"]},
]


async def seed():
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///apptrail.db")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession)
    async with factory() as session:
        count = 0
        for u in UMBRELLAS:
            existing = await session.execute(
                select(RoleUmbrella).where(RoleUmbrella.name == u["name"])
            )
            if not existing.scalar_one_or_none():
                session.add(RoleUmbrella(
                    name=u["name"],
                    aliases=u.get("aliases"),
                    typical_skills=u.get("typical_skills"),
                ))
                count += 1
        await session.commit()
        print(f"Seeded {count} umbrella categories ({len(UMBRELLAS)} total defined)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
