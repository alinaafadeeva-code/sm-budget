import streamlit as st
import pandas as pd
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

st.set_page_config(page_title='ФОТ — Детализация', page_icon='👤', layout='wide')
from utils.auth import check_password, show_logout_button

if not check_password():
    st.stop()
show_logout_button()

from utils.sheets import save_salary_details, load_salary_details
from utils.mappings import MONTHS_RU
from utils.ui import sidebar_period

st.title('👤 ФОТ — Детализация по сотрудникам')
st.caption('Загружай реестры выплат СЗ — фильтруй по сотруднику, отделу, периоду.')

year, month = sidebar_period()


# ── Парсер файла СЗ ────────────────────────────────────────────────────────────
def parse_salary_file(file_obj, year: int, month: int, pay_date: str) -> list[dict]:
    """
    Читает реестр выплат формата 'СЗ ДД.ММ.ГГ.xls':
      Кол 0: Вид деятельности (отдел)
      Кол 2: ФИО
      Кол 3: Оклад
      Кол 4: Допвыплаты
      Кол 9: Итого к выплате СЗ
      Кол 10: Примечания
    Строка заголовков — row 2 (index 2).
    """
    try:
        df = pd.read_excel(file_obj, header=None, dtype=str, engine='xlrd')
    except Exception:
        df = pd.read_excel(file_obj, header=None, dtype=str)

    records = []
    current_dept = ''

    for i, row in df.iterrows():
        if i < 3:   # пропускаем шапку (строки 0-2)
            continue

        dept_raw = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
        name_raw = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
        amt_raw  = row.iloc[9] if len(row) > 9 else None

        # Строка итогов — останавливаемся
        if dept_raw.upper() == 'ИТОГО':
            break

        # Обновляем текущий отдел если он указан
        if dept_raw and dept_raw.lower() not in ('nan', '0', ''):
            current_dept = dept_raw

        # Пропускаем пустые строки без имени
        if not name_raw or name_raw.lower() in ('nan', ''):
            continue

        # Сумма к выплате
        try:
            amount = float(str(amt_raw).replace(' ', '').replace(',', '.').strip())
        except (ValueError, TypeError):
            amount = 0.0

        if amount <= 0:
            continue

        # Оклад и допвыплаты
        try:
            base = float(str(row.iloc[3]).replace(' ', '').replace(',', '.').strip())
        except (ValueError, TypeError):
            base = 0.0
        try:
            add = float(str(row.iloc[4]).replace(' ', '').replace(',', '.').strip())
        except (ValueError, TypeError):
            add = 0.0

        notes = str(row.iloc[10]).strip() if len(row) > 10 and pd.notna(row.iloc[10]) else ''
        if notes.lower() == 'nan':
            notes = ''

        records.append({
            'year':        year,
            'month':       month,
            'pay_date':    pay_date,
            'department':  current_dept,
            'name':        name_raw,
            'base_salary': round(base, 2),
            'additional':  round(add, 2),
            'amount':      round(amount, 2),
            'notes':       notes,
        })

    return records


# ── Вкладки ────────────────────────────────────────────────────────────────────
tab_upload, tab_view = st.tabs(['📤 Загрузить реестр', '📊 Просмотр и фильтры'])


# ══ Загрузка ══════════════════════════════════════════════════════════════════
with tab_upload:
    st.subheader('Загрузить реестр выплат СЗ')
    st.caption('Формат: файлы типа «СЗ 20.05.26.xls» — отдел в кол. A, ФИО в кол. C, '
               'итого к выплате в кол. J')

    col1, col2 = st.columns([1, 1])
    with col1:
        upload_year  = st.number_input('Год', min_value=2024, max_value=2030,
                                       value=year, key='sal_det_year')
        upload_month = st.selectbox('Месяц', options=list(MONTHS_RU.keys()),
                                    format_func=lambda x: MONTHS_RU[x],
                                    index=month - 1, key='sal_det_month')
    with col2:
        pay_date = st.text_input('Дата выплаты (из имени файла)', placeholder='20.05.2026')

    uploaded = st.file_uploader('Выбери файл реестра', type=['xls', 'xlsx'],
                                 key='sal_det_file')

    if uploaded:
        # Авто-определяем дату из имени файла если не указана
        if not pay_date:
            m = re.search(r'(\d{1,2})[\.\-](\d{1,2})[\.\-](\d{2,4})', uploaded.name)
            if m:
                d, mo, yr = m.groups()
                yr_full = f'20{yr}' if len(yr) == 2 else yr
                pay_date = f'{d.zfill(2)}.{mo.zfill(2)}.{yr_full}'

        with st.spinner('Читаю файл…'):
            records = parse_salary_file(uploaded, int(upload_year), int(upload_month),
                                        pay_date or '')

        if not records:
            st.error('Не удалось найти записи. Проверь формат файла.')
        else:
            st.success(f'Найдено сотрудников: **{len(records)}**')

            # Предпросмотр
            df_prev = pd.DataFrame(records)
            st.dataframe(
                df_prev[['department', 'name', 'base_salary', 'additional', 'amount', 'notes']]
                .rename(columns={
                    'department': 'Отдел', 'name': 'ФИО',
                    'base_salary': 'Оклад', 'additional': 'Доп.',
                    'amount': 'Итого к выплате', 'notes': 'Примечания',
                }),
                hide_index=True, use_container_width=True, height=350,
            )

            total = sum(r['amount'] for r in records)
            st.metric('💰 Итого к выплате', f'{total:,.0f} ₽'.replace(',', ' '))

            if st.button('💾 Сохранить', type='primary', use_container_width=True):
                with st.spinner('Сохраняю…'):
                    save_salary_details(records, int(upload_year), int(upload_month))
                st.success(f'✅ Сохранено {len(records)} записей за '
                           f'{MONTHS_RU[int(upload_month)]} {upload_year}')


# ══ Просмотр ══════════════════════════════════════════════════════════════════
with tab_view:
    df = load_salary_details()

    if df.empty:
        st.info('Данных пока нет. Загрузи реестры выплат на вкладке «Загрузить реестр».')
        st.stop()

    st.subheader('Фильтры')
    fc1, fc2, fc3, fc4 = st.columns(4)

    with fc1:
        f_year = st.selectbox('Год', sorted(df['year'].unique(), reverse=True), key='fv_year')

    months_avail = sorted(df[df['year'] == f_year]['month'].unique())
    with fc2:
        f_month = st.selectbox(
            'Месяц', ['Все'] + months_avail,
            format_func=lambda x: 'Все месяцы' if x == 'Все' else MONTHS_RU.get(x, x),
            key='fv_month',
        )

    depts = sorted(df['department'].dropna().unique())
    with fc3:
        f_dept = st.selectbox('Отдел', ['Все'] + depts, key='fv_dept')

    with fc4:
        f_name = st.text_input('Поиск по ФИО', placeholder='Фамилия…', key='fv_name')

    # Применяем фильтры
    view = df[df['year'] == f_year].copy()
    if f_month != 'Все':
        view = view[view['month'] == f_month]
    if f_dept != 'Все':
        view = view[view['department'] == f_dept]
    if f_name:
        view = view[view['name'].str.contains(f_name, case=False, na=False)]

    st.divider()

    # Итоги по фильтру
    c1, c2, c3 = st.columns(3)
    c1.metric('👤 Сотрудников', len(view))
    c2.metric('💰 Итого выплачено', f'{view["amount"].sum():,.0f} ₽'.replace(',', ' '))
    c3.metric('📅 Дат выплат', view['pay_date'].nunique())

    # Таблица
    st.dataframe(
        view[['pay_date', 'department', 'name', 'base_salary', 'additional', 'amount', 'notes']]
        .rename(columns={
            'pay_date': 'Дата', 'department': 'Отдел', 'name': 'ФИО',
            'base_salary': 'Оклад ₽', 'additional': 'Доп. ₽',
            'amount': 'Выплачено ₽', 'notes': 'Примечания',
        })
        .sort_values(['pay_date', 'department', 'Выплачено ₽'], ascending=[True, True, False])
        .style.format({
            'Оклад ₽':     lambda x: f'{x:,.0f}'.replace(',', ' '),
            'Доп. ₽':      lambda x: f'{x:,.0f}'.replace(',', ' '),
            'Выплачено ₽': lambda x: f'{x:,.0f}'.replace(',', ' '),
        }),
        hide_index=True, use_container_width=True, height=500,
    )

    # Сводка по отделам
    st.divider()
    st.markdown('**По отделам**')
    by_dept = (view.groupby('department')['amount']
               .agg(['sum', 'count'])
               .rename(columns={'sum': 'Итого ₽', 'count': 'Чел.'})
               .sort_values('Итого ₽', ascending=False))
    by_dept['Итого ₽'] = by_dept['Итого ₽'].apply(lambda x: f'{x:,.0f}'.replace(',', ' '))
    st.dataframe(by_dept, use_container_width=True)
