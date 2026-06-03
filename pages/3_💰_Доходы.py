import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import save_revenue, load_revenue, get_occupancy_dict, clear_caches
from utils.mappings import (
    STUDIO_CODES, ENTITY_STUDIOS, ENTITY_NAMES,
    REVENUE_CATEGORIES, MONTHS_RU, STUDIO_ENTITY,
    AVG_TRAINING_PRICE, MANUAL_REVENUE_STUDIOS, OCCUPANCY_STUDIOS,
)
from utils.ui import sidebar_period

st.set_page_config(page_title='Доходы', page_icon='💰', layout='wide')
st.title('💰 Ввод доходов')

year, month = sidebar_period()

entity_filter = st.selectbox(
    'Юрлицо',
    options=['Все'] + list(ENTITY_NAMES.keys()),
    format_func=lambda x: 'Все юрлица' if x == 'Все'
                           else f'{x} — {ENTITY_NAMES[x]}',
)

st.divider()

occ      = get_occupancy_dict(year, month)
existing = load_revenue()

if occ:
    st.info(
        f'📊 Заполняемость за {MONTHS_RU[month]} {year} загружена. '
        f'Абонементы рассчитаны автоматически: визиты × {AVG_TRAINING_PRICE:,} ₽. '
        f'Бар и массаж — введи вручную.'
    )
else:
    st.warning(
        f'⚠️ Заполняемость за {MONTHS_RU[month]} {year} не введена — '
        'абонементы не рассчитаются автоматически.'
    )

# Категории для таблицы — без «прочих поступлений» (206), они вводятся отдельно
CAT_TABLE = {code: name for code, name in REVENUE_CATEGORIES.items() if code != 206}
CAT_SHORT = {code: name.replace('Выручка ', '') for code, name in CAT_TABLE.items()}

all_records = []

for entity_key, entity_studios in ENTITY_STUDIOS.items():
    if entity_filter != 'Все' and entity_key != entity_filter:
        continue

    st.subheader(ENTITY_NAMES[entity_key])

    rows = {}
    for studio in entity_studios:
        row = {}
        for cat_code, cat_name_short in CAT_SHORT.items():
            saved = None
            if not existing.empty:
                m = (
                    (existing['year']          == year)  &
                    (existing['month']         == month) &
                    (existing['studio']        == studio) &
                    (existing['category_code'] == cat_code)
                )
                if m.any():
                    saved = float(existing[m]['amount'].iloc[0])

            if saved is None and cat_code == 201 and studio not in MANUAL_REVENUE_STUDIOS:
                visits = occ.get(studio, 0)
                row[cat_name_short] = float(visits * AVG_TRAINING_PRICE) if visits > 0 else 0.0
            else:
                row[cat_name_short] = saved if saved is not None else 0.0

        rows[STUDIO_CODES[studio]] = row

    df_in = pd.DataFrame(rows).T
    df_in.index.name = 'Студия'

    col_cfg = {
        col: st.column_config.NumberColumn(col, format='%d', min_value=0, step=1000)
        for col in df_in.columns
    }

    edited = st.data_editor(
        df_in, column_config=col_cfg, use_container_width=True,
        key=f'revenue_editor_{entity_key}_{year}_{month}', num_rows='fixed',
    )

    totals = edited.sum()
    total_str = '  |  '.join(
        f'{CAT_SHORT[c]}: **{int(totals[CAT_SHORT[c]]):,}**'.replace(',', ' ')
        for c in CAT_TABLE
        if totals[CAT_SHORT[c]] > 0
    )
    if total_str:
        st.caption(f'Итого: {total_str}')

    for studio_name, row in edited.iterrows():
        studio_code = next((s for s in entity_studios if STUDIO_CODES[s] == studio_name), None)
        if not studio_code:
            continue
        for cat_code, cat_name_short in CAT_SHORT.items():
            val = float(row[cat_name_short])
            if val > 0:
                all_records.append({
                    'year': year, 'month': month,
                    'entity': entity_key,
                    'studio': studio_code,
                    'category_code': cat_code,
                    'amount': val,
                })

# ── Прочие поступления — распределение по заполняемости ───────────────────────
st.divider()
st.subheader('💫 Прочие поступления')
st.caption('Введи общую сумму — система распределит по всем студиям согласно коэффициенту заполняемости')

# Загружаем сохранённое значение (сумма всех studio-записей категории 206)
saved_misc_total = 0.0
if not existing.empty:
    m206 = (
        (existing['year']          == year) &
        (existing['month']         == month) &
        (existing['category_code'] == 206)
    )
    if m206.any():
        saved_misc_total = float(existing[m206]['amount'].sum())

misc_total = st.number_input(
    'Всего прочих поступлений, ₽',
    min_value=0, step=1000,
    value=int(saved_misc_total),
    key=f'misc_revenue_{year}_{month}',
)

if misc_total > 0:
    if occ:
        # Считаем коэффициенты по всем студиям сети
        total_visits = sum(occ.get(s, 0) for s in OCCUPANCY_STUDIOS)
        if total_visits > 0:
            misc_rows_preview = []
            for studio in OCCUPANCY_STUDIOS:
                visits = occ.get(studio, 0)
                if visits <= 0:
                    continue
                share = round(misc_total * visits / total_visits, 2)
                entity_key = STUDIO_ENTITY.get(studio, '—')
                misc_rows_preview.append({
                    'Студия': STUDIO_CODES.get(studio, studio),
                    'Визитов': visits,
                    'Коэффициент': f'{visits/total_visits*100:.1f}%',
                    'Сумма, ₽': f'{share:,.0f}'.replace(',', ' '),
                })
                all_records.append({
                    'year': year, 'month': month,
                    'entity': entity_key,
                    'studio': studio,
                    'category_code': 206,
                    'amount': share,
                })
            with st.expander('📊 Распределение по студиям', expanded=False):
                st.dataframe(pd.DataFrame(misc_rows_preview), hide_index=True, use_container_width=True)
        else:
            st.warning('Нет данных заполняемости для распределения.')
    else:
        st.warning(f'⚠️ Введи заполняемость за {MONTHS_RU[month]} {year} — тогда сумма разнесётся автоматически.')

st.divider()
grand_total = sum(r['amount'] for r in all_records)
st.metric('💰 Итого доходов', f'{grand_total:,.0f} ₽'.replace(',', ' '))

if st.button('💾 Сохранить доходы', type='primary', use_container_width=True):
    if not all_records:
        st.warning('Нет данных для сохранения.')
    else:
        with st.spinner('Сохраняю…'):
            save_revenue(all_records)
            clear_caches()
        st.success(f'✅ Сохранено записей: {len(all_records)}')
