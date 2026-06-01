import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import save_revenue, load_revenue, get_occupancy_dict, clear_caches
from utils.mappings import (
    STUDIO_CODES, ENTITY_STUDIOS, ENTITY_NAMES,
    REVENUE_CATEGORIES, MONTHS_RU, STUDIO_ENTITY,
    AVG_TRAINING_PRICE, MANUAL_REVENUE_STUDIOS,
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

# Загружаем заполняемость для авторасчёта абонементов
occ = get_occupancy_dict(year, month)
if occ:
    st.info(
        f'📊 Заполняемость за {MONTHS_RU[month]} {year} загружена. '
        f'Выручка абонементов рассчитана автоматически: визиты × {AVG_TRAINING_PRICE:,} ₽. '
        f'Бар и массаж — вводи вручную.'
    )
else:
    st.warning(
        f'⚠️ Заполняемость за {MONTHS_RU[month]} {year} не введена. '
        'Внеси её на странице «Заполняемость» — тогда выручка абонементов подставится автоматически.'
    )

existing = load_revenue()

# Проверяем есть ли уже сохранённые данные за этот месяц
has_saved = False
if not existing.empty:
    mask = (existing['year'] == year) & (existing['month'] == month)
    if entity_filter != 'Все':
        mask &= existing['entity'] == entity_filter
    has_saved = existing[mask].any().any()
    if has_saved:
        st.info(f'ℹ️ За {MONTHS_RU[month]} {year} уже внесены доходы — показаны сохранённые значения.')

st.subheader(f'Выручка за {MONTHS_RU[month]} {year}')

records = []

for entity_key, entity_studios in ENTITY_STUDIOS.items():
    if entity_filter != 'Все' and entity_key != entity_filter:
        continue

    st.markdown(f'**{ENTITY_NAMES[entity_key]}**')
    cols_header = st.columns([2] + [1] * len(REVENUE_CATEGORIES))

    cols_header[0].markdown('*Студия*')
    for i, (cat_code, cat_name) in enumerate(REVENUE_CATEGORIES.items()):
        cols_header[i + 1].markdown(f'*{cat_name.replace("Выручка ", "")}*')

    for studio in entity_studios:
        studio_name = STUDIO_CODES[studio]
        cols = st.columns([2] + [1] * len(REVENUE_CATEGORIES))
        cols[0].write(studio_name)

        for i, (cat_code, cat_name) in enumerate(REVENUE_CATEGORIES.items()):
            # Ищем сохранённое значение
            existing_val = None
            if not existing.empty:
                mask2 = (
                    (existing['year'] == year) &
                    (existing['month'] == month) &
                    (existing['studio'] == studio) &
                    (existing['category_code'] == cat_code)
                )
                if mask2.any():
                    existing_val = float(existing[mask2]['amount'].iloc[0])

            # Авторасчёт абонементов: визиты × средняя цена
            # Только для студий не из ручного списка (не бар, не массаж)
            if existing_val is None and cat_code == 201 and studio not in MANUAL_REVENUE_STUDIOS:
                visits = occ.get(studio, 0)
                default_val = float(visits * AVG_TRAINING_PRICE) if visits > 0 else 0.0
            else:
                default_val = existing_val if existing_val is not None else 0.0

            val = cols[i + 1].number_input(
                f'{studio}_{cat_code}',
                min_value=0.0,
                value=default_val,
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
