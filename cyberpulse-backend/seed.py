"""Create a demo instructor, a demo student and one published quiz.

Usage:  python seed.py
"""

from app.database import SessionLocal, init_db
from app.models import Quiz, User, utcnow
from app.security import hash_password


def main() -> None:
    init_db()
    db = SessionLocal()

    def ensure_user(email: str, name: str, role: str) -> User:
        user = db.query(User).filter(User.email == email).first()
        if user:
            return user
        user = User(
            name=name,
            email=email,
            role=role,
            hashed_password=hash_password("password123"),
            provider="password",
            onboarding_completed=True,
            university="University of Jordan",
            major="Cybersecurity",
            last_active=utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    instructor = ensure_user("instructor@cyberpulse.dev", "Dr. Lina Haddad", "Instructor")
    ensure_user("student@cyberpulse.dev", "Salsabeel Deeb", "Student")

    if not db.get(Quiz, "quiz-networking-basics"):
        db.add(
            Quiz(
                id="quiz-networking-basics",
                title="Network Security Fundamentals",
                description="Check your understanding of ports, protocols and basic recon.",
                created_by=str(instructor.id),
                author_id=instructor.id,
                published=True,
                time_limit=600,
                questions=[
                    {
                        "id": "q1",
                        "text": "Which port does HTTPS use by default?",
                        "type": "mcq",
                        "options": ["21", "80", "443", "8080"],
                        "correctAnswer": 2,
                        "points": 2,
                    },
                    {
                        "id": "q2",
                        "text": "A SYN scan completes the full TCP handshake.",
                        "type": "truefalse",
                        "options": ["True", "False"],
                        "correctAnswer": 1,
                        "points": 1,
                    },
                ],
            )
        )
        db.commit()

    print("Seed complete.")
    print("  Instructor: instructor@cyberpulse.dev / password123")
    print("  Student:    student@cyberpulse.dev / password123")
    db.close()


if __name__ == "__main__":
    main()
