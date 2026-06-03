import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import load_expenses, load_revenue, load_salaries
from utils.mappings import (
    STUDIO_CODES, ENTITY_NAMES, ENTITY_STUDIOS,
    ALL_EXPENSE_CATEGORIES, REVENUE_CATEGORIES,
    MONTHS_RU, ENTITY_COLORS, ACQUIRING_RATE,
)
from utils.ui import sidebar_period

st.set_page_config(page_title='Дашборд', page_icon='📊', layout='wide')
st.title('📊 Дашборд')


def fmt(val):
    if val >= 1_000_000:
        return f'{val/1_000_000:.1f} млн ₽'
    return f'{val:,.0f} ₽'.replace(',', ' ')


def fmt_delta(val):
    sign = '+' if val >= 0 else ''
    return f'{sign}{val/1_000_000:.1f} млн ₽' if abs(val) >= 1_000_000 else f'{sign}{val:,.0f} ₽'.replace(',', ' ')


exp_df = load_expenses()
rev_df = load_revenue()
sal_df = load_salaries()

# ── Ремаппинг категорий для данных января–мая 2026 ───────────────────────────
# До июня 2026 бухгалтер использовал другую нумерацию статей.
# С 01.06.2026 — текущая нумерация (mappings.py).
# Коды 1–8 и 42–46 совпадают в обеих системах, коды 9–41 — сдвинуты.
_CAT_MAP_JAN_MAY_2026 = {
     9: 41,  # Хоз. принадлежности
    10: 40,  # Малоценные
    11:  9,  # Средства личной гигиены
    12: 10,  # Расходные материалы
    13: 11,  # Реклама
    14: 12,  # Бухгалтерское обслуживание
    15: 13,  # Эквайринг
    16: 14,  # Химчистка полотенец
    17: 15,  # Продукты для бара
    18: 16,  # Прочие услуги
    19: 17,  # Прочие расходы
    20: 18,  # Лизинг/кредит
    21: 19,  # Инвест расходы
    22: 20,  # Форма персонал
    23: 21,  # Спортивный инвентарь
    24: 22,  # Офисные расходы
    25: 23,  # Регистрация/снятие ккм/ккт
    26: 24,  # Возврат займа
    27: 25,  # Инвест займы
    28: 26,  # ТО и ремонт
    29: 27,  # Монтаж и установка оборудования
    30: 28,  # Мелкое оборудование
    31: 29,  # Оборудование
    32: 30,  # Оборудование орг техника
    33: 31,  # Вывоз мусора
    34: 32,  # РАО и ВОИС
    35: 33,  # Транспортные расходы
    36: 34,  # Корпоративные расходы
    37: 35,  # HR (вакансии)
    38: 36,  # Программное обеспечение
    39: 37,  # Юр расходы
    40: 38,  # Цветы, украшение студий
    41: 39,  # Полиграфия
}
if not exp_df.empty:
    _old_period = (exp_df['year'] == 2026) & (exp_df['month'] <= 5)
    _remap = _old_period & exp_df['category_code'].isin(_CAT_MAP_JAN_MAY_2026)
    exp_df.loc[_remap, 'category_code'] = (
        exp_df.loc[_remap, 'category_code'].map(_CAT_MAP_JAN_MAY_2026)
    )

if exp_df.empty and rev_df.empty:
    st.info('Данных пока нет. Загрузи реестры платежей и введи доходы.')
    st.stop()


# ── Фильтры и настройки ────────────────────────────────────────────────────────
year, month = sidebar_period()

with st.sidebar:
    st.header('Дополнительно')
    view_mode = st.radio('Период', ['Месяц', 'С начала года (YTD)'])

    if view_mode == 'Месяц':
        months_range = [month]
    else:
        max_month = st.slider(
            'По месяц включительно', 1, 12,
            value=month,
            format=lambda x: MONTHS_RU[x],
        )
        months_range = list(range(1, max_month + 1))

    studio_filter = st.selectbox(
        'Студия',
        ['Все'] + list(STUDIO_CODES.keys()),
        format_func=lambda x: 'Все студии' if x == 'Все' else STUDIO_CODES[x],
    )
    entity_filter = st.selectbox(
        'Юрлицо',
        ['Все'] + list(ENTITY_NAMES.keys()),
        format_func=lambda x: 'Все' if x == 'Все' else f'{x} — {ENTITY_NAMES[x]}',
    )

    st.divider()
    st.markdown('**👔 Расходы руководителей**')
    mgmt_expenses = st.number_input(
        'Сумма, ₽',
        min_value=0, step=10_000,
        key=f'mgmt_exp_{year}_{"-".join(map(str, months_range))}',
        help='Вычитаются из чистой прибыли → итог к распределению',
        label_visibility='collapsed',
    )


# ── Фильтрация ─────────────────────────────────────────────────────────────────
def filter_df(df):
    if df is None or df.empty:
        return pd.DataFrame()
    mask = (df['year'] == year) & (df['month'].isin(months_range))
    if studio_filter != 'Все':
        mask &= df['studio'] == studio_filter
    if entity_filter != 'Все':
        mask &= df['entity'] == entity_filter
    return df[mask].copy()


exp_f = filter_df(exp_df)
rev_f = filter_df(rev_df)
sal_f = filter_df(sal_df)

# ── Разбивка расходов по уровням P&L ──────────────────────────────────────────
# Полностью исключены: переводы, займы (не расходы)
FULLY_EXCLUDED  = {0, 24, 25, 27}
# Ниже операц. прибыли: налоги, инвест расходы, проценты
BELOW_LINE_CATS = {19, 43, 44, 45}

if not exp_f.empty:
    exp_f_oper  = exp_f[~exp_f['category_code'].isin(FULLY_EXCLUDED | BELOW_LINE_CATS)]
    exp_f_below = exp_f[exp_f['category_code'].isin(BELOW_LINE_CATS)]
    exp_f_show  = exp_f[~exp_f['category_code'].isin(FULLY_EXCLUDED)]  # для графиков
else:
    exp_f_oper = exp_f_below = exp_f_show = pd.DataFrame()

# ── Эквайринг ─────────────────────────────────────────────────────────────────
if not rev_f.empty:
    acq_by_studio = rev_f.groupby('studio')['amount'].sum().mul(ACQUIRING_RATE).round(2)
    total_acquiring = acq_by_studio.sum()
else:
    acq_by_studio = pd.Series(dtype=float)
    total_acquiring = 0.0

# ── P&L расчёт ────────────────────────────────────────────────────────────────
total_revenue  = rev_f['amount'].sum()         if not rev_f.empty      else 0.0
total_oper_exp = (
    (exp_f_oper['amount'].sum() if not exp_f_oper.empty else 0.0) +
    (sal_f['amount'].sum()      if not sal_f.empty      else 0.0) +
    total_acquiring
)
oper_profit  = total_revenue - total_oper_exp
oper_margin  = (oper_profit / total_revenue * 100) if total_revenue > 0 else 0.0

below_total  = exp_f_below['amount'].sum() if not exp_f_below.empty else 0.0
net_profit   = oper_profit - below_total
net_margin   = (net_profit / total_revenue * 100) if total_revenue > 0 else 0.0

final_result = net_profit - mgmt_expenses
final_margin = (final_result / total_revenue * 100) if total_revenue > 0 else 0.0

period_label = (
    MONTHS_RU[months_range[0]] if len(months_range) == 1
    else f'Январь – {MONTHS_RU[months_range[-1]]}'
)


# ── KPI: Операционный уровень ──────────────────────────────────────────────────
st.subheader(f'{period_label} {year}')

c1, c2, c3, c4 = st.columns(4)
c1.metric('💚 Доходы', fmt(total_revenue))
c2.metric('🔴 Операц. расходы', fmt(total_oper_exp),
          help=f'Включает эквайринг {ACQUIRING_RATE*100:.0f}% = {fmt(total_acquiring)}')
c3.metric('🏆 Операц. прибыль', fmt(oper_profit),
          delta=f'{oper_margin:.1f}% маржа',
          delta_color='normal' if oper_profit >= 0 else 'inverse')
c4.metric('📉 Операц. маржа', f'{oper_margin:.0f}%' if total_revenue > 0 else '—')

# ── KPI: Чистая прибыль ────────────────────────────────────────────────────────
st.divider()

# Разбивка "ниже линии"
below_items = []
if not exp_f_below.empty:
    exp_f_below2 = exp_f_below.copy()
    exp_f_below2['cat_name'] = exp_f_below2['category_code'].map(
        lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else '?'
    )
    for cat, grp in exp_f_below2.groupby('cat_name'):
        below_items.append(f'{cat}: {fmt(grp["amount"].sum())}')

c5, c6, c7, c8 = st.columns(4)
c5.metric(
    '💸 Налоги и фин. расходы', fmt(below_total),
    help='\n'.join(below_items) if below_items else 'Нет данных',
)
c6.metric('👔 Расходы руководителей', fmt(mgmt_expenses))
c7.metric('💰 Чистая прибыль', fmt(net_profit),
          delta=f'{net_margin:.1f}% маржа',
          delta_color='normal' if net_profit >= 0 else 'inverse')
c8.metric('✅ Итог к распределению', fmt(final_result),
          delta=f'{final_margin:.1f}%',
          delta_color='normal' if final_result >= 0 else 'inverse')

st.divider()


# ── Вкладки ────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(['По студиям', 'По статьям', 'Динамика', 'Сводная таблица'])


# ══ Вкладка 1: По студиям ══════════════════════════════════════════════════════
with tab1:
    # P&L по студиям использует только операционные расходы
    all_exp_oper = pd.concat([d for d in [exp_f_oper, sal_f] if not d.empty], ignore_index=True) \
        if (not exp_f_oper.empty or not sal_f.empty) else pd.DataFrame()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('**Расходы по студиям (операционные)**')
        if not all_exp_oper.empty:
            exp_by_studio = (
                all_exp_oper[all_exp_oper['studio'].isin(STUDIO_CODES)]
                .groupby('studio')['amount'].sum()
            )
            exp_by_studio = exp_by_studio.add(acq_by_studio, fill_value=0).reset_index()
            exp_by_studio.columns = ['studio', 'amount']
            exp_by_studio['studio_name'] = exp_by_studio['studio'].map(STUDIO_CODES)
            exp_by_studio = exp_by_studio.dropna(subset=['studio_name']).sort_values('amount', ascending=True)
            fig = px.bar(exp_by_studio, x='amount', y='studio_name', orientation='h',
                         color='amount', color_continuous_scale='Reds',
                         labels={'amount': 'Сумма ₽', 'studio_name': ''})
            fig.update_layout(showlegend=False, coloraxis_showscale=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info('Нет данных')

    with col_right:
        st.markdown('**Доходы по студиям**')
        if not rev_f.empty:
            rev_by_studio = rev_f.groupby('studio')['amount'].sum().reset_index()
            rev_by_studio['studio_name'] = rev_by_studio['studio'].map(lambda x: STUDIO_CODES.get(x, x))
            rev_by_studio = rev_by_studio.sort_values('amount', ascending=True)
            fig2 = px.bar(rev_by_studio, x='amount', y='studio_name', orientation='h',
                          color='amount', color_continuous_scale='Greens',
                          labels={'amount': 'Сумма ₽', 'studio_name': ''})
            fig2.update_layout(showlegend=False, coloraxis_showscale=False, height=400)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info('Нет данных')

    st.markdown('**P&L по студиям (операционный)**')
    if not rev_f.empty and not all_exp_oper.empty:
        rev_s = rev_f.groupby('studio')['amount'].sum()
        exp_s = all_exp_oper[all_exp_oper['studio'].isin(STUDIO_CODES)].groupby('studio')['amount'].sum()
        exp_s = exp_s.add(acq_by_studio, fill_value=0)
        pnl_rows = []
        for s in set(rev_s.index) | set(exp_s.index):
            r = rev_s.get(s, 0)
            e = exp_s.get(s, 0)
            pnl_rows.append({'studio': STUDIO_CODES.get(s, s), 'Доходы': r, 'Расходы': e, 'Прибыль': r - e})
        pnl_df = pd.DataFrame(pnl_rows).sort_values('Прибыль', ascending=False)
        fig3 = go.Figure()
        fig3.add_bar(name='Доходы',  x=pnl_df['studio'], y=pnl_df['Доходы'],  marker_color='#10B981')
        fig3.add_bar(name='Расходы', x=pnl_df['studio'], y=pnl_df['Расходы'], marker_color='#EF4444')
        fig3.update_layout(barmode='group', height=380, xaxis_tickangle=-30)
        st.plotly_chart(fig3, use_container_width=True)


# ══ Вкладка 2: По статьям ══════════════════════════════════════════════════════
with tab2:
    # Показываем все значимые расходы (операц. + ниже линии)
    all_exp_show = pd.concat([d for d in [exp_f_show, sal_f] if not d.empty], ignore_index=True) \
        if (not exp_f_show.empty or not sal_f.empty) else pd.DataFrame()

    if not all_exp_show.empty or total_acquiring > 0:
        if not all_exp_show.empty:
            all_exp_show['category_name'] = all_exp_show['category_code'].map(
                lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else 'Без статьи'
            )
            cat_sum = all_exp_show.groupby('category_name')['amount'].sum().reset_index()
        else:
            cat_sum = pd.DataFrame(columns=['category_name', 'amount'])

        if total_acquiring > 0:
            acq_label = f'Эквайринг (расч. {ACQUIRING_RATE*100:.0f}%)'
            cat_sum = pd.concat([cat_sum,
                pd.DataFrame([{'category_name': acq_label, 'amount': total_acquiring}])
            ], ignore_index=True)

        cat_sum = cat_sum.sort_values('amount', ascending=False).head(20)
        fig4 = px.bar(cat_sum.sort_values('amount', ascending=True),
                      x='amount', y='category_name', orientation='h',
                      color='amount', color_continuous_scale='Blues',
                      labels={'amount': 'Сумма ₽', 'category_name': ''},
                      title='Топ-20 статей расходов')
        fig4.update_layout(height=600, coloraxis_showscale=False)
        st.plotly_chart(fig4, use_container_width=True)

        fig5 = px.pie(cat_sum, values='amount', names='category_name', title='Структура расходов')
        fig5.update_layout(height=500)
        st.plotly_chart(fig5, use_container_width=True)
    else:
        st.info('Нет данных о расходах')


# ══ Вкладка 3: Динамика ════════════════════════════════════════════════════════
with tab3:
    def monthly_series(df, label, exclude_cats=None):
        if df is None or df.empty:
            return pd.DataFrame(columns=['month', label])
        mask = (df['year'] == year)
        if studio_filter != 'Все':
            mask &= df['studio'] == studio_filter
        if entity_filter != 'Все':
            mask &= df['entity'] == entity_filter
        sub = df[mask]
        if exclude_cats:
            sub = sub[~sub['category_code'].isin(exclude_cats)]
        s = sub.groupby('month')['amount'].sum().reset_index()
        s.columns = ['month', label]
        return s

    rev_monthly  = monthly_series(rev_df, 'Доходы')
    exp_monthly  = monthly_series(exp_df, 'Операц. расходы', exclude_cats=FULLY_EXCLUDED | BELOW_LINE_CATS)
    sal_monthly  = monthly_series(sal_df, 'ЗП')
    blow_monthly = monthly_series(exp_df, 'Налоги и фин.', exclude_cats=
                                  {c for c in range(100) if c not in BELOW_LINE_CATS})

    if not rev_df.empty:
        rev_mask = (rev_df['year'] == year)
        if studio_filter != 'Все':
            rev_mask &= rev_df['studio'] == studio_filter
        if entity_filter != 'Все':
            rev_mask &= rev_df['entity'] == entity_filter
        acq_monthly = (rev_df[rev_mask].groupby('month')['amount'].sum()
                       .mul(ACQUIRING_RATE).round(2).reset_index())
        acq_monthly.columns = ['month', 'Эквайринг']
    else:
        acq_monthly = pd.DataFrame(columns=['month', 'Эквайринг'])

    months_all = pd.DataFrame({'month': list(range(1, 13))})
    merged = months_all.merge(rev_monthly, on='month', how='left')
    merged = merged.merge(exp_monthly, on='month', how='left')
    merged = merged.merge(sal_monthly, on='month', how='left')
    merged = merged.merge(acq_monthly, on='month', how='left')
    merged = merged.merge(blow_monthly, on='month', how='left')
    merged = merged.fillna(0)
    merged['Операц. расходы всего'] = merged.get('Операц. расходы', 0) + merged.get('ЗП', 0) + merged.get('Эквайринг', 0)
    merged['Операц. прибыль'] = merged['Доходы'] - merged['Операц. расходы всего']
    merged['Чистая прибыль']  = merged['Операц. прибыль'] - merged.get('Налоги и фин.', 0)
    merged['month_name'] = merged['month'].map(MONTHS_RU)

    fig6 = go.Figure()
    fig6.add_scatter(x=merged['month_name'], y=merged['Доходы'],
                     name='Доходы', line=dict(color='#10B981', width=2.5), mode='lines+markers')
    fig6.add_scatter(x=merged['month_name'], y=merged['Операц. расходы всего'],
                     name='Операц. расходы', line=dict(color='#EF4444', width=2.5), mode='lines+markers')
    fig6.add_scatter(x=merged['month_name'], y=merged['Операц. прибыль'],
                     name='Операц. прибыль', line=dict(color='#3B82F6', width=2, dash='dot'), mode='lines+markers')
    fig6.add_scatter(x=merged['month_name'], y=merged['Чистая прибыль'],
                     name='Чистая прибыль', line=dict(color='#8B5CF6', width=2, dash='dash'), mode='lines+markers')
    fig6.update_layout(height=420, xaxis_title='', yaxis_title='₽', hovermode='x unified')
    st.plotly_chart(fig6, use_container_width=True)

    merged['Доходы YTD']          = merged['Доходы'].cumsum()
    merged['Операц. расходы YTD'] = merged['Операц. расходы всего'].cumsum()
    merged['Чистая прибыль YTD']  = merged['Чистая прибыль'].cumsum()

    fig7 = go.Figure()
    fig7.add_scatter(x=merged['month_name'], y=merged['Доходы YTD'],
                     name='Доходы YTD', line=dict(color='#10B981'), fill='tonexty')
    fig7.add_scatter(x=merged['month_name'], y=merged['Операц. расходы YTD'],
                     name='Расходы YTD', line=dict(color='#EF4444'))
    fig7.add_scatter(x=merged['month_name'], y=merged['Чистая прибыль YTD'],
                     name='Чистая прибыль YTD', line=dict(color='#8B5CF6', dash='dash'))
    fig7.update_layout(height=350, title='Накопительный итог (YTD)', xaxis_title='')
    st.plotly_chart(fig7, use_container_width=True)


# ══ Вкладка 4: Сводная таблица ════════════════════════════════════════════════
with tab4:
    st.markdown('**Расходы: статья × студия**')
    all_exp_show2 = pd.concat([d for d in [exp_f_show, sal_f] if not d.empty], ignore_index=True) \
        if (not exp_f_show.empty or not sal_f.empty) else pd.DataFrame()

    if not all_exp_show2.empty or total_acquiring > 0:
        if not all_exp_show2.empty:
            all_exp_show2['category_name'] = all_exp_show2['category_code'].map(
                lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else 'Без статьи'
            )
            # Нераспределённые расходы (ОБЩ СЕТЬ и т.п.) показываем в колонке «Общие»
            all_exp_show2['studio_name'] = all_exp_show2['studio'].map(
                lambda s: STUDIO_CODES.get(s, 'Общие')
            )
            pivot = all_exp_show2.pivot_table(
                index='category_name', columns='studio_name',
                values='amount', aggfunc='sum', fill_value=0,
            )
        else:
            pivot = pd.DataFrame()

        if total_acquiring > 0:
            acq_label = f'Эквайринг (расч. {ACQUIRING_RATE*100:.0f}%)'
            acq_row = {STUDIO_CODES.get(s, s): round(v, 0) for s, v in acq_by_studio.items() if s in STUDIO_CODES}
            acq_df = pd.DataFrame([acq_row], index=[acq_label])
            if pivot.empty:
                pivot = acq_df
            else:
                for col in acq_df.columns:
                    if col not in pivot.columns:
                        pivot[col] = 0
                pivot = pd.concat([pivot, acq_df.reindex(columns=pivot.columns, fill_value=0)])

        if not pivot.empty:
            pivot['ИТОГО'] = pivot.sum(axis=1)
            pivot = pivot.sort_values('ИТОГО', ascending=False)
            fmt_fn = lambda x: f'{x:,.0f}'.replace(',', ' ')
            try:
                styled = pivot.style.format(fmt_fn).background_gradient(
                    cmap='Reds', subset=[c for c in pivot.columns if c != 'ИТОГО'])
                st.dataframe(styled, use_container_width=True, height=500)
            except Exception:
                _map = getattr(pivot, 'map', None) or pivot.applymap
                st.dataframe(_map(fmt_fn), use_container_width=True, height=500)
    else:
        st.info('Нет данных о расходах')

    st.markdown('**Доходы: категория × студия**')
    if not rev_f.empty:
        rev_f2 = rev_f.copy()
        rev_f2['category_name'] = rev_f2['category_code'].map(
            lambda x: REVENUE_CATEGORIES.get(int(x), f'Кат. {x}') if pd.notna(x) else 'Без категории'
        )
        rev_f2['studio_name'] = rev_f2['studio'].map(lambda x: STUDIO_CODES.get(x, x))
        pivot2 = rev_f2.pivot_table(
            index='category_name', columns='studio_name',
            values='amount', aggfunc='sum', fill_value=0,
        )
        pivot2['ИТОГО'] = pivot2.sum(axis=1)
        fmt_fn2 = lambda x: f'{x:,.0f}'.replace(',', ' ')
        try:
            styled2 = pivot2.style.format(fmt_fn2).background_gradient(cmap='Greens')
            st.dataframe(styled2, use_container_width=True)
        except Exception:
            _map2 = getattr(pivot2, 'map', None) or pivot2.applymap
            st.dataframe(_map2(fmt_fn2), use_container_width=True)
