import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import save_revenue, load_revenue, clear_caches
from utils.mappings import (
    STUDIO_CODES, ENTITY_STUDIOS, ENTITY_NAMES,
    REVENUE_CATEGORIES, MONTHS_RU, STUDIO_ENTITY,
)
import pandas as pd

st.set_page_config(page_title='Доходы', page_icon='💰', layout='wide')
st.title('💰 Ввод доходов')

col1, col2, col3 = st.columns(3)
with col1:
    year = st.number_input('Год', min_value=2024, max_value=2030, value=2026)
with col2:
    month = st.selectbox('Месяц', options=list(MONTHS_RU.keys()), format_func=lambda x: MONTHS_RU[x])
with col3:
    entity_filter = st.selectbox(
        'Юрлицо',
        options=['Все'] + list(ENTITY_NAMES.keys()),
        format_func=lambda x: 'Все юрлица' if x == 'Все' else f'{x} — {ENTITY_NAMES[x]}',
    )

st.divider()

# Формируем список студий
if entity_filter == 'Все':
    studios = list(STUDIO_CODES.keys())
else:
    studios = ENTITY_STUDIOS.get(entity_filter, [])

# Показываем существующие данные
existing = load_revenue()
if not existing.empty:
    mask = (existing['year'] == year) & (existing['month'] == month)
    if entity_filter != 'Все':
        mask &= existing['entity'] == entity_filter
    existing_month = existing[mask]
    if not existing_month.empty:
        st.info(f'ℹ️ За {MONTHS_RU[month]} {year} уже внесено {len(existing_month)} записей о доходах.')

# Форма ввода
st.subheader(f'Выручка за {MONTHS_RU[month]} {year}')

records = []
for entity_key, entity_studios in ENTITY_STUDIOS.items():
    if entity_filter != 'Все' and entity_key != entity_filter:
        continue

    st.markdown(f'**{ENTITY_NAMES[entity_key]}**')
    cols_header = st.columns([2] + [1] * len(REVENUE_CATEGORIES))

    # Шапка
    cols_header[0].markdown('*Студия*')
    for i, (cat_code, cat_name) in enumerate(REVENUE_CATEGORIES.items()):
        cols_header[i + 1].markdown(f'*{cat_name.replace("Выручка ", "")}*')

    for studio in entity_studios:
        studio_name = STUDIO_CODES[studio]
        cols = st.columns([2] + [1] * len(REVENUE_CATEGORIES))
        cols[0].write(studio_name)
        for i, (cat_code, cat_name) in enumerate(REVENUE_CATEGORIES.items()):
            # Предзаполняем существующим значением
            existing_val = 0.0
            if not existing.empty:
                mask2 = (
                    (existing['year'] == year) &
                    (existing['month'] == month) &
                    (existing['studio'] == studio) &
                    (existing['category_code'] == cat_code)
                )
                if mask2.any():
                    existing_val = float(existing[mask2]['amount'].iloc[0])

            val = cols[i + 1].number_input(
                f'{studio}_{cat_code}',
                min_value=0.0,
                value=existing_val,
                step=1000.0,
                label_visibility='collapsed',
                key=f'rev_{entity_key}_{studio}_{cat_code}_{year}_{month}',
            )
            if val > 0:
                records.append({
                    'year': year,
                    'month': month,
                    'entity': entity_key,
                    'studio': studio,
                    'category_code': cat_code,
                    'amount': val,
                })

    st.markdown('')

st.divider()
total = sum(r['amount'] for r in records)
st.metric('Итого доходов', f'{total:,.0f} ₽'.replace(',', ' '))

if st.button('💾 Сохранить доходы', type='primary', use_container_width=True):
    if not records:
        st.warning('Нет данных для сохранения.')
    else:
        with st.spinner('Сохраняю…'):
            save_revenue(records)
            clear_caches()
        st.success(f'✅ Сохранено записей: {len(records)}')
