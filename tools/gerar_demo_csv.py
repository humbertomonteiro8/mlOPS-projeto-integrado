"""Gera um CSV DEMO sintético (sem PII) espelhando o esquema do dataset da disciplina.

Serve para exercitar o pipeline de treino em qualquer máquina sem o train.csv real.
Não contém Name/SSN/Customer_ID reais; é apenas dados fictícios para demonstração.
Como é pequeno e artificial, normalmente NÃO alcança F1 >= 0,70 (sem promoção).

Uso: python tools/gerar_demo_csv.py  ->  escreve data/raw/demo_train.csv
"""
from __future__ import annotations

import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "demo_train.csv"
ROWS_PER_CUSTOMER = 12
N_CUSTOMERS = 36
SEED = 7

OCCUPATIONS = [
    "Scientist", "Teacher", "Engineer", "Lawyer", "Accountant", "Doctor",
    "Manager", "Mechanical_engineer", "Designer", "Architect", "Entrepreneur",
    "Developer", "Writer", "Civil servant", "Media_Manager", "Others",
]
LOAN_COMBOS = [
    "Auto Loan", "Credit-Builder Loan", "Personal Loan",
    "Home Equity Loan", "Debt Consolidation Loan", "Student Loan",
    "Mortgage Loan", "Payday Loan", "Personal Loan, Auto Loan",
    "Credit-Builder Loan, Personal Loan", "Student Loan, Personal Loan",
    "Mortgage Loan, Auto Loan",
]
BEHAVIOURS = [
    "Low_spent_Small_value_payments", "High_spent_Large_value_payments",
    "High_spent_Medium_value_payments", "Low_spent_Medium_value_payments",
    "High_spent_Small_value_payments", "Low_spent_Large_value_payments",
]

HEADER = [
    "Customer_ID", "Month", "Age", "Annual_Income", "Monthly_Inhand_Salary",
    "Num_Bank_Accounts", "Num_Credit_Card", "Interest_Rate", "Num_of_Loan",
    "Delay_from_due_date", "Num_of_Delayed_Payment", "Changed_Credit_Limit",
    "Num_Credit_Inquiries", "Outstanding_Debt", "Credit_Utilization_Ratio",
    "Total_EMI_per_month", "Amount_invested_monthly", "Monthly_Balance",
    "Occupation", "Type_of_Loan", "Credit_Mix", "Payment_of_Min_Amount",
    "Payment_Behaviour", "Credit_History_Age", "Credit_Score",
]


def risk_score(rng: random.Random, base: dict) -> float:
    """Soma ponderada simples para que Credit_Score tenha correlação com as features."""
    score = 0.0
    score += base["delay"] * 1.5
    score += base["delayed"] * 0.8
    score += base["utilization"] * 0.35
    score += base["interest"] * 0.4
    score += base["inquiries"] * 1.2
    if base["mix"] == "Bad":
        score += 14
    elif base["mix"] == "Good":
        score -= 12
    if base["pay_min"] == "No":
        score += 8
    if base["behaviour"].startswith("High_spent"):
        score += 5
    if base["behaviour"].startswith("Low_spent"):
        score -= 4
    score -= base["income"] * 0.004
    score += rng.gauss(0, 6)
    return score


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    for cust in range(1, N_CUSTOMERS + 1):
        # Perfil do cliente definido uma vez; oscilação leve por mês.
        age = rng.randint(21, 68)
        monthly_income = rng.randint(18, 90) * 100.0
        annual = rng.uniform(0.7, 2.2) * monthly_income * 12
        mix = rng.choices(["Good", "Standard", "Bad"], weights=[0.32, 0.42, 0.26])[0]
        pay_min = rng.choices(["Yes", "No"], weights=[0.62, 0.38])[0]
        behaviour = rng.choice(BEHAVIOURS)
        history_years = rng.randint(1, 26)
        history_months = rng.randint(0, 11)
        base = {
            "delay": rng.randint(0, 12),
            "delayed": rng.randint(0, 16),
            "utilization": rng.uniform(1, 65),
            "interest": rng.randint(1, 24),
            "inquiries": rng.uniform(0, 12),
            "income": monthly_income,
            "mix": mix,
            "pay_min": pay_min,
            "behaviour": behaviour,
        }
        targets = {"Good": 0, "Poor": 0, "Standard": 0}
        for month in range(1, ROWS_PER_CUSTOMER + 1):
            r = risk_score(rng, base)
            label = "Good" if r <= 8 else ("Poor" if r >= 20 else "Standard")
            targets[label] += 1
            n_bank = rng.randint(1, 8)
            n_card = rng.randint(0, 9)
            n_loan = rng.randint(0, 8)
            emi = rng.uniform(20, 120) if n_loan else 0.0
            debt = rng.uniform(0, 2500)
            balance = max(0.0, monthly_income - emi - rng.uniform(100, 900))
            rows.append([
                f"C000{cust:03d}", f"Jan-{2021 + (month - 1) // 12}",
                age, round(annual, 2), round(monthly_income, 2),
                n_bank, n_card, base["interest"], n_loan,
                rng.randint(0, base["delay"] + 3), rng.randint(0, base["delayed"] + 5),
                round(rng.uniform(2, 18), 2), round(base["inquiries"], 1),
                round(debt, 2), round(base["utilization"], 2), round(emi, 2),
                round(rng.uniform(10, 300), 2), round(balance, 2),
                rng.choice(OCCUPATIONS), rng.choice(LOAN_COMBOS), mix, pay_min,
                behaviour, f"{history_years} Years and {history_months} Months",
                label,
            ])
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        import csv
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print(f"Gerado {OUT} com {len(rows)} linhas ({N_CUSTOMERS} clientes x {ROWS_PER_CUSTOMER} meses), seed {SEED}.")


if __name__ == "__main__":
    main()