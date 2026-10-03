import sys, os, time, io
sys.path.insert(0, os.path.dirname(__file__))
from resume_cases import CASES
from app.tools.resume_parser import extract_resume_text
from app.agents.resume_agent import analyze_resume

real = extract_resume_text("C:/Users/dhair/Downloads/SivaSaiAkhilesh_MTS.pdf")["text"]
fails = 0
for name, text, years, level in CASES:
    if name == "long_resume_repeated":
        text = (real + "\n") * 4
    t0 = time.time()
    try:
        p = analyze_resume(text)
        ok_years = years is None or abs(p.total_experience_years - years) <= 0.5
        ok_level = level is None or p.career_level == level
        status = "PASS" if ok_years and ok_level else "FAIL"
        extra = f"years={p.total_experience_years} (exp {years}) level={p.career_level} (exp {level}) periods={[(x.role,x.start,x.end) for x in p.full_time_periods]} projects={len(p.projects)}"
    except Exception as e:
        status = "ERROR"; extra = f"{type(e).__name__}: {str(e)[:300]}"
    if status != "PASS": fails += 1
    print(f"{status:5} {name:34} {time.time()-t0:4.1f}s  {extra}", flush=True)
print("DONE failures:", fails, flush=True)
