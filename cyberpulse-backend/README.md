# CyberPulse Backend (FastAPI)

Backend كامل مبني ليطابق تماماً عقد الـ API الموجود في الفرونت (`src/lib/api.ts`).
ما في أي تغيير مطلوب على كود الفرونت — بس شغّل السيرفر وحدّد `VITE_API_URL`.

## التشغيل محلياً

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # عدّل JWT_SECRET على الأقل
python seed.py              # اختياري: بيانات تجريبية
uvicorn app.main:app --reload --port 8000
```

ثم في الفرونت:

```
VITE_API_URL=http://localhost:8000
```

توثيق تفاعلي: http://localhost:8000/docs

## Docker

```bash
docker build -t cyberpulse-api .
docker run -p 8000:8000 --env-file .env cyberpulse-api
```

## الـ Endpoints

| Method | Path | الوصف |
|---|---|---|
| POST | `/api/auth/register` | إنشاء حساب (Student / Instructor) |
| POST | `/api/auth/login` | تسجيل دخول → JWT |
| GET | `/api/auth/me` | بيانات المستخدم الحالي |
| PATCH | `/api/auth/me` | تحديث الملف الشخصي / إنهاء الـ onboarding |
| POST | `/api/auth/logout` | تسجيل خروج |
| GET | `/api/auth/google` | بدء Google Sign-In |
| GET | `/api/auth/google/callback` | يرجّع للفرونت `/auth-callback?token=...` |
| GET | `/api/auth/github?token=` | ربط حساب GitHub للـ portfolio |
| POST | `/api/auth/github/disconnect` | فك الربط |
| GET | `/api/quizzes?published_only=` | قائمة الكويزات |
| GET | `/api/quizzes/{id}` | كويز واحد |
| POST | `/api/quizzes` | إنشاء/تعديل كويز (Instructor) |
| DELETE | `/api/quizzes/{id}` | حذف كويز (Instructor) |
| POST | `/api/quizzes/{id}/submit` | تسليم إجابات + تصحيح تلقائي |
| GET | `/api/quizzes/{id}/submissions` | كل التسليمات (Instructor) |
| GET | `/api/quizzes/{id}/my-submission` | تسليم الطالب نفسه |
| GET | `/api/progress` | تقدّم الطالب بكل المختبرات |
| PUT | `/api/progress/{lab_id}` | حفظ/تحديث تقدّم مختبر |
| GET | `/api/dashboard` | إحصائيات لوحة الطالب |
| POST | `/api/mentor/ask` | AI Mentor (SSE streaming) |
| GET | `/api/instructor/overview` | إحصائيات عامة للدكتور |
| GET | `/api/instructor/students` | جدول الطلاب + مؤشرات النزاهة |
| GET | `/api/health` | فحص صحة السيرفر |

## المميزات المطبّقة

- **JWT Auth** مع bcrypt، وأدوار Student / Instructor محمية على مستوى الـ endpoint.
- **Google OAuth** كامل (state + code exchange) يرجّع للفرونت بنفس رموز الأخطاء
  اللي بتتوقعها صفحة `/auth-callback` (`state_mismatch`, `no_code`, `config`...).
- **GitHub OAuth** لربط حساب الطالب لعرض الـ portfolio العام للشركات.
- **AI Detection** (`app/ai_detection.py`): سكور نزاهة أكاديمية 0-100 محسوب من
  سرعة الإجابة، انتظام التوقيت بين الأسئلة، ومقارنة وقت الطالب بوسيط الشعبة.
  شفّاف وقابل للشرح للدكتور، مش صندوق أسود.
- **Question-level time tracking**: `question_times` بتنبعت مع التسليم وبتنخزن
  وبتُستخدم في حساب الـ AI detection.
- **Adaptive AI Mentor**: مستوى المساعدة بيتدرّج حسب `hintsUsed`
  (تلميح مفاهيمي → توجيه → خطوات → شرح كامل)، مع بث SSE. بيشتغل بدون مفتاح
  OpenAI باستخدام تلميحات مدمجة، وبيستخدم الـ LLM لما تحط `OPENAI_API_KEY`.
- **Instructor analytics** محسوبة من بيانات حقيقية (مش mock).

## ملاحظات إنتاج

- بدّل `DATABASE_URL` لـ PostgreSQL بالإنتاج (`postgresql+psycopg://...`).
- `JWT_SECRET` لازم يكون عشوائي طويل ومخزّن كـ secret.
- الـ Docker labs المعزولة بتحتاج Docker daemon على السيرفر — الطبقة الحالية
  بتخزّن التقدّم والنتائج؛ تشغيل الحاويات بينضاف كخدمة منفصلة (runner) لأن
  تشغيلها لازم يكون على host فيه Docker socket، مش داخل الـ API نفسه.
