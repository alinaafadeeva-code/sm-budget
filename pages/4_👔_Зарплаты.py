import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import save_salaries, load_salaries, clear_caches
from utils.mappings import (
    ENTITY_STUDIOS, ENTITY_NAMES, STUDIO_CODES,
    SALARY_CATEGORIES, MONTHS_RU,
)
import pandas as pd

st.set_page_config(page_title='Зарплаты', page_icon='👔', layout='wide')
st.title('👔 Зарплаты')
st.markdown('Вноси данные **раз в месяц** после его завершения.')

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

existing = load_salaries()
records = []

for entity_key, entity_studios in ENTITY_STUDIOS.items():
    if entity_filter != 'Все' and entity_key != entity_filter:
        continue

    st.subheader(ENTITY_NAMES[entity_key])

    # Таблица: строки = студии, колонки = категории ЗП
    for cat_code, cat_name in SALARY_CATEGORIES.items():
        st.markdown(f'**{cat_name}**')
        cols = st.columns(len(entity_studios))

        for i, studio in enumerate(entity_studios):
            studio_name = STUDIO_CODES[studio]
            existing_val = 0.0
            if not existing.empty:
                mask = (
                    (existing['year'] == year) &
                    (existing['month'] == month) &
                    (existing['studio'] == studio) &
                    (existing['category_code'] == cat_code)
                )
                if mask.any():
                    existing_val = float(existing[mask]['amount'].iloc[0])

            val = cols[i].number_input(
                studio_name,
                min_value=0.0,
                value=existing_val,
                step=1000.0,
                key=f'sal_{entity_key}_{studio}_{cat_code}_{year}_{month}',
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
st.metric('Итого ФОТ', f'{total:,.0f} ₽'.replace(',', ' '))

if st.button('💾 Сохранить зарплаты', type='primary', use_container_width=True):
    if not records:
        st.warning('Нет данных для сохранения.')
    else:
        with st.spinner('Сохраняю…'):
            save_salaries(records)
            clear_caches()
        st.success(f'✅ Сохранено записей: {len(records)}')
