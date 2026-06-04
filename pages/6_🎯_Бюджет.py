import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import save_budget, load_budget
from utils.mappings import MONTHS_RU
from utils.ui import sidebar_period

st.set_page_config(page_title='Бюджет / План', page_icon='🎯', layout='wide')
from utils.auth import check_password, show_logout_button

if not check_password():
    st.stop()
show_logout_button()

st.title('🎯 Бюджет / План')
st.caption('Вводи плановые показатели по месяцам — без разбивки по студиям. '
           'Дашборд будет сравнивать факт с планом и подсвечивать отклонения.')

year, _ = sidebar_period()

# ── Загружаем существующий план ───────────────────────────────────────────────
existing = load_budget()

LINES = {
    'revenue':    '💚 Выручка (план)',
    'salary':     '👥 ФОТ (план)',
    'expenses':   '🔴 Операц. расходы без ФОТ (план)',
    'below_line': '💸 Налоги и фин. расходы (план)',
    'mgmt':       '👔 Расходы руководителей (план)',
}

# Формируем DataFrame для редактирования: строки = метрики, колонки = месяцы
months = list(MONTHS_RU.keys())       # 1..12
month_names = list(MONTHS_RU.values())

data = {}
for line in LINES:
    row = {}
    for m in months:
        val = 0.0
        if not existing.empty:
            mask = (
                (existing['year']  == year) &
                (existing['month'] == m) &
                (existing['line']  == line)
            )
            if mask.any():
                val = float(existing[mask]['amount'].iloc[0])
        row[MONTHS_RU[m]] = val
    data[LINES[line]] = row

df_edit = pd.DataFrame(data).T
df_edit.index.name = 'Показатель'

col_cfg = {
    col: st.column_config.NumberColumn(col, format='%d', min_value=0, step=100_000)
    for col in df_edit.columns
}

st.subheader(f'Плановые показатели {year}')
st.caption('Суммы в рублях. Авторасчёт: Плановая прибыль = Выручка − ФОТ − Расходы − Налоги − Руководители')

edited = st.data_editor(
    df_edit, column_config=col_cfg,
    use_container_width=True, num_rows='fixed',
    key=f'budget_editor_{year}',
)

# Авторасчёт плановой прибыли
rev_row  = edited.loc[LINES['revenue']]
sal_row  = edited.loc[LINES['salary']]
exp_row  = edited.loc[LINES['expenses']]
bel_row  = edited.loc[LINES['below_line']]
mgmt_row = edited.loc[LINES['mgmt']]
profit_row = rev_row - sal_row - exp_row - bel_row - mgmt_row

st.divider()
st.subheader('Плановая прибыль к распределению (авторасчёт)')
profit_display = profit_row.to_frame().T
profit_display.index = ['✅ Итог к распределению (план)']
profit_display.index.name = 'Показатель'

def color_profit(val):
    if val < 0:
        return 'color: #DC2626; font-weight: 700'
    return 'color: #065F46; font-weight: 700'

styler = profit_display.style.format(lambda x: f'{x:,.0f}'.replace(',', ' '))
try:
    styler = styler.map(color_profit)       # pandas >= 2.1
except AttributeError:
    styler = styler.applymap(color_profit)  # pandas < 2.1
st.dataframe(styler, use_container_width=True)

# Годовые итоги
st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric('💚 Выручка год',    f'{rev_row.sum():,.0f} ₽'.replace(',', ' '))
c2.metric('🔴 Расходы год',    f'{(sal_row + exp_row + bel_row + mgmt_row).sum():,.0f} ₽'.replace(',', ' '))
c3.metric('✅ Прибыль год',    f'{profit_row.sum():,.0f} ₽'.replace(',', ' '))
c4.metric('📊 Плановая маржа', f'{profit_row.sum()/rev_row.sum()*100:.1f}%'
          if rev_row.sum() > 0 else '—')

# ── Сохранение ────────────────────────────────────────────────────────────────
if st.button('💾 Сохранить план', type='primary', use_container_width=True):
    records = []
    line_keys = list(LINES.keys())
    for i, line in enumerate(line_keys):
        row_label = LINES[line]
        for m in months:
            val = float(edited.loc[row_label, MONTHS_RU[m]])
            if val > 0:
                records.append({
                    'year': year, 'month': m,
                    'line': line, 'amount': val,
                })
    if not records:
        st.warning('Все значения нулевые — нечего сохранять.')
    else:
        with st.spinner('Сохраняю план…'):
            save_budget(year, records)
        st.success(f'✅ План на {year} год сохранён ({len(records)} записей).')
