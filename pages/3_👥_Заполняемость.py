import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import save_occupancy, load_occupancy, get_occupancy_dict, load_expenses, save_expenses, clear_caches
from utils.processor import apply_occupancy
from utils.mappings import OCCUPANCY_STUDIOS, STUDIO_CODES, MONTHS_RU
from utils.ui import sidebar_period
import pandas as pd

st.set_page_config(page_title='Заполняемость', page_icon='👥', layout='wide')
st.title('👥 Заполняемость студий')
st.markdown('Вводи данные **1–2 числа** нового месяца. После сохранения общие расходы прошлого месяца будут автоматически разнесены по студиям.')

year, month = sidebar_period()

# Загружаем существующие данные
existing = get_occupancy_dict(year, month)

st.divider()
st.subheader(f'Количество визитов за {MONTHS_RU[month]} {year}')

visits = {}
total_visits = 0

cols = st.columns(3)
for i, studio in enumerate(OCCUPANCY_STUDIOS):
    col = cols[i % 3]
    default_val = existing.get(studio, 0)
    val = col.number_input(
        STUDIO_CODES.get(studio, studio),
        min_value=0,
        value=default_val,
        step=10,
        key=f'occ_{studio}_{year}_{month}',
    )
    visits[studio] = val
    total_visits += val

st.divider()
col_total, col_btn = st.columns([1, 2])
col_total.metric('Итого визитов', f'{total_visits:,}'.replace(',', ' '))

# Показываем коэффициенты
if total_visits > 0:
    with st.expander('📊 Коэффициенты распределения'):
        coef_data = []
        for studio, v in visits.items():
            if v > 0:
                coef_data.append({
                    'Студия': STUDIO_CODES.get(studio, studio),
                    'Визитов': v,
                    'Коэффициент': f'{v/total_visits*100:.1f}%',
                })
        st.dataframe(pd.DataFrame(coef_data), use_container_width=True, hide_index=True)

if st.button('💾 Сохранить и разнести расходы', type='primary', use_container_width=True):
    if total_visits == 0:
        st.warning('Введи хотя бы один ненулевой показатель.')
    else:
        with st.spinner('Сохраняю заполняемость и пересчитываю общие расходы…'):
            save_occupancy(year, month, {k: v for k, v in visits.items() if v > 0})

            # Пересчитываем общие расходы за этот месяц
            all_expenses = load_expenses()
            occ_dict = {k: v for k, v in visits.items() if v > 0}

            if not all_expenses.empty:
                mask = (
                    (all_expenses['year'] == year) &
                    (all_expenses['month'] == month) &
                    (all_expenses['studio'].isin(['', 'ОБЩ', 'ОБЩ СЕТЬ']))
                )
                general_txns = all_expenses[mask].to_dict('records')
                if general_txns:
                    allocated = apply_occupancy(general_txns, occ_dict)
                    save_expenses(allocated)

            clear_caches()
        st.success(f'✅ Заполняемость сохранена. Общие расходы разнесены по коэффициентам.')
