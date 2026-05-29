import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# Названия листов в Google Sheets
SH_EXPENSES   = 'expenses'
SH_REVENUE    = 'revenue'
SH_SALARIES   = 'salaries'
SH_OCCUPANCY  = 'occupancy'

EXPENSE_HEADERS  = ['date','year','month','entity','studio','category_code','amount','description','type']
REVENUE_HEADERS  = ['year','month','entity','studio','category_code','amount']
SALARY_HEADERS   = ['year','month','entity','studio','category_code','amount']
OCCUPANCY_HEADERS= ['year','month','studio','visits']


@st.cache_resource
def get_client():
    creds = Credentials.from_service_account_info(
        st.secrets['gcp_service_account'], scopes=SCOPES
    )
    return gspread.authorize(creds)


@st.cache_resource
def get_spreadsheet():
    client = get_client()
    return client.open_by_key(st.secrets['spreadsheet_id'])


def _get_or_create_sheet(name: str, headers: list):
    ss = get_spreadsheet()
    try:
        ws = ss.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=10000, cols=len(headers))
        ws.append_row(headers, value_input_option='RAW')
    return ws


def _sheet_to_df(name: str, headers: list) -> pd.DataFrame:
    ws = _get_or_create_sheet(name, headers)
    # UNFORMATTED_VALUE — сырые числа без локального форматирования.
    # Без этого gspread читает "2537,49" (рус. формат) и убирает запятую
    # как разделитель тысяч → 253749 вместо 2537.49 (ошибка ×100).
    data = ws.get_all_records(
        expected_headers=headers,
        value_render_option='UNFORMATTED_VALUE',
    )
    if not data:
        return pd.DataFrame(columns=headers)
    return pd.DataFrame(data)


# ─── Расходы ──────────────────────────────────────────────────────────────────

def save_expenses(records: list):
    """Сохраняет расходы, заменяя старые записи за то же юрлицо + год + месяц."""
    ws = _get_or_create_sheet(SH_EXPENSES, EXPENSE_HEADERS)
    if not records:
        return

    # Собираем уникальные (entity, year, month) из новых записей
    keys = {(r['entity'], r['year'], r['month']) for r in records}

    # Удаляем существующие записи с теми же ключами
    df = _sheet_to_df(SH_EXPENSES, EXPENSE_HEADERS)
    if not df.empty:
        mask = pd.Series([False] * len(df))
        for entity, year, month in keys:
            mask |= (
                (df['entity'].astype(str) == str(entity)) &
                (df['year'].astype(str) == str(year)) &
                (df['month'].astype(str) == str(month))
            )
        if mask.any():
            ws.clear()
            ws.append_row(EXPENSE_HEADERS)
            keep = df[~mask]
            if not keep.empty:
                ws.append_rows(keep.values.tolist(), value_input_option='RAW')

    rows = [[r.get(h, '') for h in EXPENSE_HEADERS] for r in records]
    ws.append_rows(rows, value_input_option='RAW')


def load_expenses() -> pd.DataFrame:
    df = _sheet_to_df(SH_EXPENSES, EXPENSE_HEADERS)
    if df.empty:
        return df
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['year']   = pd.to_numeric(df['year'],   errors='coerce').fillna(0).astype(int)
    df['month']  = pd.to_numeric(df['month'],  errors='coerce').fillna(0).astype(int)
    df['category_code'] = pd.to_numeric(df['category_code'], errors='coerce')
    return df


# ─── Доходы ───────────────────────────────────────────────────────────────────

def save_revenue(records: list):
    ws = _get_or_create_sheet(SH_REVENUE, REVENUE_HEADERS)
    rows = [[r.get(h, '') for h in REVENUE_HEADERS] for r in records]
    ws.append_rows(rows, value_input_option='RAW')


def load_revenue() -> pd.DataFrame:
    df = _sheet_to_df(SH_REVENUE, REVENUE_HEADERS)
    if df.empty:
        return df
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['year']   = pd.to_numeric(df['year'],   errors='coerce').fillna(0).astype(int)
    df['month']  = pd.to_numeric(df['month'],  errors='coerce').fillna(0).astype(int)
    return df


# ─── Зарплаты ─────────────────────────────────────────────────────────────────

def save_salaries(records: list):
    """Сохраняет зарплаты за месяц, заменяя старые записи за тот же период."""
    ws = _get_or_create_sheet(SH_SALARIES, SALARY_HEADERS)
    if not records:
        return
    year  = records[0]['year']
    month = records[0]['month']

    # Удаляем существующие записи за этот год/месяц
    df = _sheet_to_df(SH_SALARIES, SALARY_HEADERS)
    if not df.empty:
        mask = (df['year'].astype(str) == str(year)) & (df['month'].astype(str) == str(month))
        if mask.any():
            ws.clear()
            ws.append_row(SALARY_HEADERS)
            keep = df[~mask]
            if not keep.empty:
                ws.append_rows(keep.values.tolist(), value_input_option='RAW')

    rows = [[r.get(h, '') for h in SALARY_HEADERS] for r in records]
    ws.append_rows(rows, value_input_option='RAW')


def load_salaries() -> pd.DataFrame:
    df = _sheet_to_df(SH_SALARIES, SALARY_HEADERS)
    if df.empty:
        return df
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['year']   = pd.to_numeric(df['year'],   errors='coerce').fillna(0).astype(int)
    df['month']  = pd.to_numeric(df['month'],  errors='coerce').fillna(0).astype(int)
    return df


# ─── Заполняемость ────────────────────────────────────────────────────────────

def save_occupancy(year: int, month: int, occupancy: dict):
    ws = _get_or_create_sheet(SH_OCCUPANCY, OCCUPANCY_HEADERS)
    # Удаляем старые записи за этот месяц
    df = _sheet_to_df(SH_OCCUPANCY, OCCUPANCY_HEADERS)
    if not df.empty:
        mask = (df['year'].astype(str) == str(year)) & (df['month'].astype(str) == str(month))
        if mask.any():
            ws.clear()
            ws.append_row(OCCUPANCY_HEADERS)
            keep = df[~mask]
            if not keep.empty:
                ws.append_rows(keep.values.tolist(), value_input_option='RAW')
    rows = [[year, month, studio, visits] for studio, visits in occupancy.items()]
    ws.append_rows(rows, value_input_option='RAW')


def load_occupancy() -> pd.DataFrame:
    df = _sheet_to_df(SH_OCCUPANCY, OCCUPANCY_HEADERS)
    if df.empty:
        return df
    df['visits'] = pd.to_numeric(df['visits'], errors='coerce').fillna(0).astype(int)
    df['year']   = pd.to_numeric(df['year'],   errors='coerce').fillna(0).astype(int)
    df['month']  = pd.to_numeric(df['month'],  errors='coerce').fillna(0).astype(int)
    return df


def get_occupancy_dict(year: int, month: int) -> dict:
    df = load_occupancy()
    if df.empty:
        return {}
    mask = (df['year'] == year) & (df['month'] == month)
    sub = df[mask]
    return dict(zip(sub['studio'], sub['visits']))


def clear_caches():
    """Оставлено для обратной совместимости — кэш убран, функция ничего не делает."""
    pass
