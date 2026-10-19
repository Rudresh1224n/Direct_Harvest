# DirectHarvest AI — From Farm to Fair Deal

> **A Complete, College-Demonstrable Agricultural Marketplace & Crop Intelligence Platform**  
> Built with **FastAPI**, **MySQL**, **SQLAlchemy 2.0**, **OpenCV Computer Vision**, **Pandas**, **openpyxl**, and **Vanilla JavaScript**.

---

## 🌾 1. Project Overview & Problem Statement

In conventional agricultural supply chains, farmers often receive only **20% to 30%** of the end-consumer price due to multiple uncoordinated intermediaries (middlemen, commission agents, brokers). Furthermore:
- Consumers pay inflated retail prices for produce of unverified quality and freshness.
- Farmers lack direct price transparency, market demand signals, and objective crop grading tools.
- Deliveries are uncoordinated, leading to transit spoilage.

**DirectHarvest AI** solves these systemic problems by connecting farmers directly with local consumers and independent delivery partners:
1. **Direct Marketplace:** Eliminates exploitative middlemen, giving farmers higher margins and consumers lower prices.
2. **AI-Assisted Crop Quality Assessment:** Uses **OpenCV computer vision** on crop photographs to compute objective HSV color distribution, surface uniformity, blemish percentages, freshness scores (68–98%), and quality grades (A+, A, B, C).
3. **Smart Mandi-Benchmarked Pricing:** Recommends fair prices based on national Agmarknet wholesale mandi rates adjusted by the visual crop grade.
4. **Transparent Farmer Trust Score:** Mathematically calculated from customer ratings, fulfillment rate, and cancellation rate.
5. **Real-Time WhatsApp Notifications:** Multi-channel alerting (Meta Cloud API, Twilio, and local database simulation) for orders, dispatch, and delivery.
6. **Dedicated Admin Governance Portal:** Live DB KPIs, user status controls, commission settings, WhatsApp telemetry logs, and styled Excel exports (`users.xlsx`, `farmer_crops.xlsx`, `orders.xlsx`).

---

## 🏛️ 2. Architectural Design & Tech Stack

```mermaid
flowchart TD
    subgraph Frontend["Frontend Layer (No Heavy Frameworks)"]
        UI["Jinja2 Server Templates + HTML5 / Modern CSS"]
        JS["Vanilla JS + Fetch API (Asynchronous API Calls)"]
    end

    subgraph Backend["FastAPI Application Layer (Python 3.12)"]
        Router["FastAPI Routers (Public, Auth, Consumer, Farmer, Delivery, Admin, API)"]
        AuthMid["JWT & bcrypt Authentication (Role Guards)"]
        AISvc["OpenCV Computer Vision (HSV & Defect Thresholding)"]
        OrderSvc["Atomic Order Engine (with_for_update Row Locking)"]
        ExcelSvc["openpyxl Styled Report Generator"]
        WASvc["WhatsApp Notification Engine (Meta / Twilio / Sim)"]
    end

    subgraph Database["Database Layer (Single Source of Truth)"]
        MySQL[("MySQL 8.0 Server (directharvest Database)")]
    end

    UI --> Router
    JS --> Router
    Router --> AuthMid
    Router --> AISvc
    Router --> OrderSvc
    Router --> ExcelSvc
    Router --> WASvc
    AuthMid --> MySQL
    OrderSvc --> MySQL
    ExcelSvc --> MySQL
    WASvc --> MySQL
```

### Technology Matrix
| Component | Technology | Rationale & Justification |
| :--- | :--- | :--- |
| **Backend Framework** | **FastAPI** (Python 3.12) | Asynchronous high-performance REST APIs, automatic OpenAPI Swagger documentation, strict Pydantic type safety. |
| **Database** | **MySQL 8.0** | Industrial relational database with ACID transactions, foreign keys, row-level locks, and check constraints. |
| **ORM & Driver** | **SQLAlchemy 2.0** + **PyMySQL** | Declarative models, relationship navigation, parameterized SQL injection prevention. |
| **Frontend** | **HTML5 + CSS3 + Vanilla JS + Jinja2** | Lightweight, zero-build compilation overhead, easily readable for college viva and inspection. |
| **Computer Vision / AI** | **OpenCV** (`opencv-python-headless`) + **NumPy** | Deterministic image processing (HSV color analysis, surface variance, dark-pixel defect detection). |
| **Data Analytics** | **Pandas** | Price distribution aggregation (min/max/average/median) and mandi market comparisons. |
| **Spreadsheet Reports**| **openpyxl** | Generates styled `.xlsx` reports with formatted headers, auto-filters, and auto-sized columns. |
| **Security** | **bcrypt** + **PyJWT** | Salted 12-round password hashing and signed JWT authentication tokens stored in HttpOnly cookies / headers. |

---

## 👥 3. User Roles & Capabilities

### 1. Public Visitor
- Browse the catalog of fresh farm produce with category, location, and price filters.
- Search crops with instant keyword filtering.
- View detailed crop specifications, OpenCV quality grade, and farmer contact info.
- Register as Consumer, Farmer, or Delivery Partner.

### 2. Consumer
- Add produce to persistent cart with real-time stock limits.
- Atomic checkout with delivery address selection and payment mode (Cash on Delivery).
- Order tracking with IST timestamps across 6 status milestones.
- Write verified star ratings and text reviews for delivered orders (duplicate reviews prevented).
- Instant WhatsApp order confirmation alerts.

### 3. Farmer
- Crop management: Add, edit, list, and delete crops.
- **OpenCV Crop Analysis:** Upload a photograph of the harvest to receive automatic freshness scoring, quality grade (A+, A, B, C), and suggested mandi pricing.
- Manage incoming orders: Accept or reject orders.
- Farmer Wallet: Tracks pending credits on order placement and auto-settles funds into available balance upon successful delivery.
- Farmer Trust Score dashboard with transparent mathematical breakdown.

### 4. Delivery Partner
- View available unassigned orders in the delivery hub.
- Accept delivery jobs.
- Update delivery statuses: `Assigned` ➔ `Picked Up` ➔ `In Transit` ➔ `Delivered`.
- View delivery instructions, customer phone, and drop-off addresses.

### 5. Administrator Portal (`/admin/dashboard`)
- Isolated administration interface with dark theme and dedicated sidebar.
- Live database KPIs: Active farmers, consumers, delivery partners, total crops, delivered revenue, and commission earned.
- User management: View all registered users and toggle account status (`Active` ⮂ `Inactive`).
- Order assignment: Allocate unassigned orders to active delivery partners.
- WhatsApp message logs: View status, recipient phone, and exact message text of sent notifications.
- Excel reports: One-click streaming download of `users.xlsx`, `farmer_crops.xlsx`, and `orders.xlsx`.

---

## 🔑 4. Demo Account Credentials

Use these verified accounts during presentations and demonstrations:

| Role | Email Address | Password | Name / Notes |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin@directharvest.com` | `admin123` | System Administrator (Full access to `/admin/*`) |
| **Farmer** | `rudresh.narkhede19@gmail.com` | `asdfghjkl;` | Rudresh Narkhede (Maharashtra) |
| **Farmer** | `krishamreliya240489@acropolis.in` | `Krish@2005` | Krish Amreliya (Madhya Pradesh) |
| **Consumer** | `lishika@gmail.com` | `asdfghjkl;` | Lishika (Pune) |
| **Consumer** | `sourabhmakwani230489@acropolis.in` | `Sourabh@2005` | Sourabh Makwani (Indore) |
| **Delivery Partner** | `rohan@gmail.com` | `qwertyuiop` | Rohan Sharma (Bike Delivery) |
| **Delivery Partner** | `labhanshgade55@gmail.com` | `Labhansh@2005` | Labhansh Gade (Van Delivery) |

---

## 🚀 5. Local Setup & Execution Guide

### Prerequisites
- Python 3.10+ (Tested on Python 3.12)
- MySQL Server 8.0 running locally on port 3306
- Git

### Step 1: Clone & Navigate to Repository
```bash
git clone https://github.com/your-username/NewDirectHarvest.git
cd NewDirectHarvest
```

### Step 2: Create Virtual Environment & Install Dependencies
**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure your MySQL credentials match `.env`:
```env
DATABASE_URL=mysql+pymysql://root:root@localhost:3306/directharvest
SECRET_KEY=directharvest-super-secret-jwt-key-2026-production
WHATSAPP_PROVIDER=simulation
PORT=7860
```

### Step 4: Initialize MySQL Database
Make sure MySQL service is running, create the database, and generate the schema:
```bash
# In MySQL CLI: CREATE DATABASE IF NOT EXISTS directharvest;
python scripts/init_db.py
```

### Step 5: (Optional) Seed Admin or Migrate Legacy Data
```bash
# Create an admin user interactively or with defaults:
python scripts/create_admin.py --email admin@directharvest.com --password admin123 --name "Super Administrator"

# Or migrate data from SQLite if needed:
python scripts/migrate_from_sqlite.py
```

### Step 6: Start Application Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 7860 --reload
```
Open your browser and navigate to:
- **Public Marketplace:** [http://localhost:7860](http://localhost:7860)
- **Admin Portal:** [http://localhost:7860/admin/login](http://localhost:7860/admin/login)
- **Interactive API Swagger Docs:** [http://localhost:7860/docs](http://localhost:7860/docs)

---

## 🧪 6. Automated Testing Suite

The repository includes a complete test suite covering authentication, crop CRUD, atomic stock updates, order lifecycles, OpenCV computer vision, and Excel exports.

Run all tests with:
```bash
pytest -v
```

### Test Coverage Highlights
- `tests/test_auth.py`: User registration, duplicate email handling, login token generation, role permission checks.
- `tests/test_crops.py`: Crop creation, category filtering, search queries, negative stock rejection.
- `tests/test_orders.py`: Cart manipulation, atomic stock deduction (`with_for_update`), order milestone progression, cancellation stock restoration.
- `tests/test_opencv.py`: Synthetic fresh and blemished image analysis, HSV metrics, defect thresholding, and graceful fallbacks.
- `tests/test_excel.py`: Valid `.xlsx` binary streaming, correct sheet names, password privacy verification.
- `tests/test_admin.py`: Dashboard KPIs, user status toggle, and report export endpoints.

---

## 🧠 7. Algorithms & Core Engineering Details

### A. OpenCV Crop Quality & Freshness Assessment (`AIService`)
1. **Resolution Normalization:** Image is resized to $300 \times 300$ pixels.
2. **HSV Color Conversion:** Converts BGR to HSV color space ($H, S, V$).
   - **Hue ($H$):** Measures dominant color tone.
   - **Saturation ($S$):** Measures color purity and vibrancy.
   - **Brightness ($V$):** Measures lighting and surface reflectance.
3. **Defect & Blemish Thresholding:**
   - Grayscale conversion and inverted binary thresholding ($\text{threshold} \le 45$) detect dark patches indicating rot, mold, or bruising.
   - $\text{Defect \%} = \left(\frac{\text{Defective Pixels}}{\text{Total Pixels}}\right) \times 100$.
4. **Surface Uniformity Score:**
   - Evaluates standard deviation of the brightness channel ($\sigma_V$).
   - $\text{Uniformity} = 100 - (\sigma_V \times 0.7)$, bounded within $[50\%, 99\%]$.
5. **Freshness Score:**
   - $\text{Freshness} = 65.0 + (0.35 \times \text{Color Vibrancy}) - (0.50 \times \text{Defect \%})$.
6. **Grade Assignment:**
   - **A+ (Premium Export):** Freshness $\ge 92\%$, Defect $< 5\%$, Uniformity $\ge 80\%$ (Price multiplier: $1.15\times$).
   - **A (High Quality):** Freshness $\ge 85\%$, Defect $< 10\%$ (Price multiplier: $1.05\times$).
   - **B (Standard Market):** Freshness $\ge 75\%$, Defect $< 18\%$ (Price multiplier: $0.95\times$).
   - **C (Processing / Discount):** Below thresholds (Price multiplier: $0.82\times$).

### B. Farmer Trust Score Formula (`TrustScoreService`)
Calculated dynamically from live MySQL orders and reviews:
$$\text{Trust Score} = (0.50 \times \text{Rating Component}) + (0.35 \times \text{Fulfillment Component}) + (0.15 \times \text{Cancellation Component})$$
Where:
- $\text{Rating Component} = \text{Average Customer Rating} \in [1.0, 5.0]$.
- $\text{Fulfillment Component} = \left(\frac{\text{Delivered Orders}}{\text{Total Accepted Orders}}\right) \times 5.0$.
- $\text{Cancellation Component} = \left(1.0 - \frac{\text{Cancelled Orders}}{\text{Total Orders}}\right) \times 5.0$.

### C. Concurrency Control & Overselling Prevention
- Uses **pessimistic row locking** via SQLAlchemy `with_for_update()` during checkout.
- MySQL places an exclusive lock on the specific crop record until the checkout transaction commits.
- If two consumers attempt to purchase the last $5\text{ kg}$ simultaneously, the second transaction is queued and immediately evaluates the updated stock, throwing an `Insufficient Stock` exception rather than producing negative inventory.

---

## 🌐 8. REST API Endpoints Overview

| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | Public | System & MySQL connection health check |
| `POST` | `/api/auth/register` | Public | Register new consumer, farmer, or delivery partner |
| `POST` | `/api/auth/login` | Public | Authenticate user and receive JWT access token |
| `GET` | `/api/auth/me` | Authenticated | Retrieve profile details of authenticated user |
| `GET` | `/api/crops` | Public | Filterable crops catalog (category, price, grade, search) |
| `GET` | `/api/crops/{id}` | Public | Detailed specifications of a specific crop |
| `POST` | `/api/crops` | Farmer | Create new crop listing |
| `POST` | `/api/analyze-crop` | Farmer | Upload image for OpenCV crop quality grading |
| `GET` | `/api/cart` | Consumer | Retrieve active shopping cart items |
| `POST` | `/api/cart` | Consumer | Add crop quantity to cart |
| `POST` | `/api/checkout` | Consumer | Atomic checkout and order placement |
| `GET` | `/api/orders` | Authenticated | Role-filtered order history |
| `POST` | `/api/orders/{id}/status` | Authenticated | Update order workflow milestone |
| `POST` | `/api/reviews` | Consumer | Submit star rating and feedback for delivered order |
| `GET` | `/admin/reports/export/{users\|crops\|orders}` | Admin | Stream styled Excel spreadsheet download |

---

## 🚢 9. Production Deployment Guide (Ubuntu / Linux)

### 1. Systemd Service Configuration
Create `/etc/systemd/system/directharvest.service`:
```ini
[Unit]
Description=DirectHarvest AI FastAPI Application
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/directharvest
Environment="PATH=/var/www/directharvest/venv/bin"
ExecStart=/var/www/directharvest/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:7860

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. Nginx Reverse Proxy Configuration
Create `/etc/nginx/sites-available/directharvest`:
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    client_max_body_size 20M;

    location /static/ {
        alias /var/www/directharvest/frontend/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 🎓 10. College Viva & Presentation Q&A Guide

### Q1: Why did you choose FastAPI instead of Django or Flask?
> **Answer:** FastAPI provides native asynchronous request processing (`async/await`), high concurrency throughput comparable to Node.js and Go, and automatic Pydantic request validation. Unlike Django, it has no heavyweight ORM bloat, allowing us to implement a clean, lightweight architecture while maintaining full control over SQLAlchemy and MySQL.

### Q2: How does the application prevent negative stock when multiple users buy the same crop simultaneously?
> **Answer:** We enforce concurrency safety using database-level pessimistic row locking via SQLAlchemy's `with_for_update()`. When a customer initiates checkout, the crop row is locked inside an ACID transaction. The stock availability is validated, decremented, and committed atomically. Additionally, MySQL check constraints (`quantity_available >= 0`) physically prohibit negative stock at the storage engine level.

### Q3: Explain how the AI crop quality assessment works without requiring expensive GPU infrastructure.
> **Answer:** Rather than deploying an oversized neural network requiring dedicated GPU servers, DirectHarvest AI uses deterministic OpenCV computer vision techniques. It maps the crop image into HSV color space to evaluate hue and color saturation, performs adaptive grayscale thresholding to identify discolored/blemished pixel patches, and calculates surface uniformity via standard deviation. This yields an objective, reproducible quality grade (A+, A, B, C) and freshness score in milliseconds on standard CPU hardware.

### Q4: How is security handled across user roles?
> **Answer:** We implement role-based access control (RBAC) via FastAPI dependencies. Passwords are never stored in plaintext; they are hashed using `bcrypt` with 12 salt rounds. Authenticated sessions issue signed JSON Web Tokens (JWT) containing the user ID. Protected endpoints verify the JWT signature and dynamically fetch the current active role from the database, preventing privilege escalation. Ordinary users cannot access administrative endpoints by modifying frontend state or URLs.

### Q5: How do WhatsApp notifications function if external credentials are not configured?
> **Answer:** The application implements a flexible strategy pattern: if Meta Cloud API or Twilio credentials are provided in `.env`, real WhatsApp messages are dispatched via HTTP. If not, the system defaults to `simulation` mode, where role-formatted messages are committed to the MySQL `whatsapp_logs` table with delivery status, recipient phone number, and timestamp. The administrator can view and monitor all notifications in real time via the Admin Portal (`/admin/notifications`).

---

## 📄 License
This project is released for academic, research, and non-commercial educational purposes.
DirectHarvest AI — *From Farm to Fair Deal.*
