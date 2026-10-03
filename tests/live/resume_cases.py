"""
Live end-to-end resume scenarios (calls the real Groq model - NOT part of the normal pytest run).
Run:  cd backend && PYTHONPATH=. venv/Scripts/python ../tests/live/run_live.py
Expected years assume today = 2026-10 (the script passes through the real date, so re-derive if rerun later).
Each case: (name, resume_text, expected_years or None, expected_level or None)
"""


CASES = [
("fresher_projects_only", """Priya Sharma  priya@example.com
Education: B.Tech Computer Science, 2026, CGPA 8.4
Skills: Python, Java, SQL, React
Projects
Library Management System - Built a CRUD app with Flask and MySQL.
Weather Dashboard - React app using OpenWeather API.
""", 0, "Fresher"),

("internship_only", """Rahul Verma  rahul@example.com
Education: B.Tech IT 2026
Experience
Software Engineering Intern, Zoho   Jan 2026 - Jun 2026
• Built REST endpoints in Java Spring Boot
Skills: Java, Spring, SQL
""", 0, "Fresher"),

("one_job_plus_two_internships", """Ankit Rao
Experience
Backend Developer, Infosys   Jul 2025 - Present
• Built microservices in Go
Internship
Data Analyst Intern, TCS   May 2024 - Aug 2024
• Dashboards in Power BI
Software Intern, Wipro   Jan 2024 - Apr 2024
• Testing automation
Skills: Go, SQL, Docker
""", 1.5, "Entry Level"),

("two_jobs_with_gap", """Meera Iyer
Experience
Software Engineer, Acme Corp   Jan 2015 - Dec 2017
• Java services
Career break (family) 2018 - 2019
Senior Software Engineer, Beta Ltd   Jan 2020 - Dec 2022
• Led a team of 4
Skills: Java, AWS
""", 6, "Senior"),

("overlapping_jobs", """Karthik N
Experience
Full-time Developer, Alpha Inc   Jan 2018 - Dec 2020
Full-time Consultant, Beta Inc   Jun 2020 - Dec 2022
Skills: Python
""", 5, "Mid Level"),

("senior_two_companies_present", """Sunita Kapoor  Engineering Manager
Experience
Staff Engineer, Gamma Co   Mar 2012 - Aug 2018
Engineering Manager, Delta Co   Oct 2018 - Present
Skills: Leadership, Java, Kubernetes
""", 14.5, "Senior"),

("numeric_dates", """Vikram Singh
Experience
Software Engineer, Foo Bar Pvt Ltd   03/2021 - Present
• Developed APIs
Skills: Node.js
""", 5.5, "Senior"),

("intern_heading_title_not_intern", """Nerella Test
Experience
Programmer/Analyst - II
NetApp, Bangalore   June 2024 - Present
• Java modules
Information Technology Internship
RPA Developer, NetApp, Bangalore   Aug 2023 - June 2024
• Built RPA bots
Skills: Java, SQL
""", 2.5, "Mid Level"),

("freelance_plus_fulltime", """Divya R
Experience
Freelance Web Developer   2019 - 2021
• Built websites for small clients
Software Engineer, Omega Tech   Jan 2022 - Dec 2023
• Full-time role, React and Node
Skills: React, Node
""", 2, "Mid Level"),

("trainee_then_fulltime", """Arjun M
Experience
Graduate Trainee, HCL   Jul 2022 - Jun 2023
Software Engineer, HCL   Jul 2023 - Present
Skills: C#, .NET
""", 3.5, "Mid Level"),

("all_caps_till_date", """RAVI KUMAR
EXPERIENCE
SOFTWARE ENGINEER - SIGMA SYSTEMS   JAN 2020 - TILL DATE
• BUILT BACKEND SERVICES
SKILLS: JAVA, SQL
""", 7, "Senior"),

("no_dates_at_all", """Sam Lee
Software engineer with 5 years of experience in Python and AWS.
Worked at Acme and Beta building data pipelines.
Skills: Python, AWS, Airflow
""", None, None),

("two_column_interleaved", """SKILLS                          EXPERIENCE
Python, SQL, Docker             Data Engineer, Zeta Corp
Airflow, Spark                  Feb 2022 - Present
EDUCATION                       • Built ETL pipelines
B.Sc Statistics 2021            • Cut costs by 30%
""", 5, None),

("garbage_long_nonresume", "The quick brown fox jumps over the lazy dog. " * 10, None, None),

("long_resume_repeated", None, None, None),  # filled in by runner (Siva text x4)
]
