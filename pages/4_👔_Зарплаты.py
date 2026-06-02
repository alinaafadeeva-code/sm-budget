import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import save_salaries, load_salaries, get_occupancy_dict, clear_caches
from utils.processor import apply_occupancy
from utils.mappings import (
    ENTITY_STUDIOS, ENTITY_NAMES, STUDIO_CODES,
    DISTRIBUTED_SALARY_CATEGORIES, DIRECT_SALARY_CATEGORIES,
    OCCUPANCY_STUDIOS, MONTHS_RU,
)
import pandas as pd

st.set_page_config(page_title='Зарплаты', page_icon='👔', layout='wide')
st.title('👔 Зарплаты')
st.markdown('Вноси данные **раз в месяц** после его завершения.')

col1, col2 = st.columns(2)
with col1:
    year = st.number_input('Год', min_value=2024, max_value=2030, value=2026, key='global_year')
with col2:
    month = st.selectbox('Месяц', options=list(MONTHS_RU.keys()), format_func=lambda x: MONTHS_RU[x], key='global_month')

existing = load_salaries()
records = []

# ── Раздел 1: Общие подразделения → распределяются по заполняемости ──────────
st.divider()
st.subheader('🔄 Общие подразделения')
st.caption('Вводишь одну сумму — система распределяет по всем студиям согласно коэффициенту заполняемости')

occ = get_occupancy_dict(year, month)
if not occ:
    st.warning(f'⚠️ Заполняемость за {MONTHS_RU[month]} {year} ещё не введена. Введи её на странице "Заполняемость" — тогда зарплаты разнесутся автоматически.')

cols = st.columns(len(DISTRIBUTED_SALARY_CATEGORIES))
dist_records = []

for i, (cat_code, cat_name) in enumerate(DISTRIBUTED_SALARY_CATEGORIES.items()):
    existing_val = 0.0
    if not existing.empty:
        mask = (
            (existing['year'] == year) &
            (existing['month'] == month) &
            (existing['studio'] == 'ОБЩ СЕТЬ') &
            (existing['category_code'] == cat_code)
        )
        if mask.any():
            existing_val = float(existing[mask]['amount'].sum())

    val = cols[i].number_input(
        cat_name,
        min_value=0.0,
        value=existing_val,
        step=1000.0,
        key=f'dist_sal_{cat_code}_{year}_{month}',
    )
    if val > 0:
        dist_records.append({
            'year': year,
            'month': month,
            'entity': 'ALL',
            'studio': 'ОБЩ СЕТЬ',
            'category_code': cat_code,
            'amount': val,
        })

total_dist = sum(r['amount'] for r in dist_records)
st.metric('Итого общие подразделения', f'{total_dist:,.0f} ₽'.replace(',', ' '))

# ── Раздел 2: Прямые зарплаты по студиям ─────────────────────────────────────
st.divider()
st.subheader('🎯 Прямые зарплаты по студиям')
st.caption('Вводишь для каждой студии отдельно')

direct_records = []

for cat_code, cat_name in DIRECT_SALARY_CATEGORIES.items():
    st.markdown(f'**{cat_name}**')
    all_studios = [s for entity_studios in ENTITY_STUDIOS.values() for s in entity_studios]
    cols2 = st.columns(min(len(all_studios), 6))

    for i, studio in enumerate(all_studios):
        col_idx = i % 6
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

        val = cols2[col_idx].number_input(
            STUDIO_CODES.get(studio, studio),
            min_value=0.0,
            value=existing_val,
            step=1000.0,
            key=f'dir_sal_{studio}_{cat_code}_{year}_{month}',
        )
        if val > 0:
            entity = next((e for e, ss in ENTITY_STUDIOS.items() if studio in ss), 'ALL')
            direct_records.append({
                'year': year,
                'month': month,
                'entity': entity,
                'studio': studio,
                'category_code': cat_code,
                'amount': val,
            })

total_direct = sum(r['amount'] for r in direct_records)
st.metric('Итого прямые зарплаты', f'{total_direct:,.0f} ₽'.replace(',', ' '))

# ── Итог и сохранение ─────────────────────────────────────────────────────────
st.divider()
total_all = total_dist + total_direct
st.metric('💰 Итого ФОТ', f'{total_all:,.0f} ₽'.replace(',', ' '))

if st.button('💾 Сохранить зарплаты', type='primary', use_container_width=True):
    all_records = dist_records + direct_records
    if not all_records:
        st.warning('Нет данных для сохранения.')
    else:
        with st.spinner('Сохраняю и распределяю по студиям…'):
            # Применяем заполняемость к общим зарплатам
            if occ and dist_records:
                dist_allocated = apply_occupancy(dist_records, occ)
            else:
                dist_allocated = dist_records  # сохраним как ОБЩ СЕТЬ, разнесём позже

            final_records = dist_allocated + direct_records
            save_salaries(final_records)
            clear_caches()
        st.success(f'✅ Сохранено. Общие подразделения {"распределены по студиям" if occ else "будут распределены после ввода заполняемости"}.')
