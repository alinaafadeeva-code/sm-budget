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
    MONTHS_RU, ENTITY_COLORS,
)

st.set_page_config(page_title='Дашборд', page_icon='📊', layout='wide')
st.title('📊 Дашборд')


def fmt(val):
    if val >= 1_000_000:
        return f'{val/1_000_000:.1f} млн ₽'
    return f'{val:,.0f} ₽'.replace(',', ' ')


# Загружаем напрямую — чтобы сброс кэша в load_expenses/revenue/salaries работал сразу
exp_df = load_expenses()
rev_df = load_revenue()
sal_df = load_salaries()

if exp_df.empty and rev_df.empty:
    st.info('Данных пока нет. Загрузи реестры платежей и введи доходы.')
    st.stop()


# ── Фильтры ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header('Фильтры')
    year = st.number_input('Год', min_value=2024, max_value=2030, value=2026, key='global_year')

    view_mode = st.radio('Период', ['Месяц', 'С начала года (YTD)'])

    if view_mode == 'Месяц':
        month = st.selectbox('Месяц', list(MONTHS_RU.keys()), format_func=lambda x: MONTHS_RU[x], key='global_month')
        months_range = [month]
    else:
        max_month = st.slider('По месяц включительно', 1, 12, 5, format=lambda x: MONTHS_RU[x])
        months_range = list(range(1, max_month + 1))
        month = None

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


exp_f  = filter_df(exp_df)
rev_f  = filter_df(rev_df)
sal_f  = filter_df(sal_df)

total_revenue  = rev_f['amount'].sum() if not rev_f.empty else 0
total_expenses = (
    (exp_f['amount'].sum() if not exp_f.empty else 0) +
    (sal_f['amount'].sum() if not sal_f.empty else 0)
)
profit = total_revenue - total_expenses
margin = (profit / total_revenue * 100) if total_revenue > 0 else 0

period_label = (
    MONTHS_RU[months_range[0]] if len(months_range) == 1
    else f'Январь – {MONTHS_RU[months_range[-1]]}'
)


# ── KPI-карточки ───────────────────────────────────────────────────────────────
st.subheader(f'{period_label} {year}')
c1, c2, c3, c4 = st.columns(4)
c1.metric('💚 Доходы',  fmt(total_revenue))
c2.metric('🔴 Расходы', fmt(total_expenses))
c3.metric(
    '🏆 Прибыль', fmt(profit),
    delta=f'{margin:.1f}% маржа',
    delta_color='normal' if profit >= 0 else 'inverse',
)
c4.metric('📉 Расходы / Доходы', f'{(total_expenses/total_revenue*100):.0f}%' if total_revenue > 0 else '—')

st.divider()


# ── Вкладки ────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(['По студиям', 'По статьям', 'Динамика', 'Сводная таблица'])


# ══ Вкладка 1: По студиям ══════════════════════════════════════════════════════
with tab1:
    # Расходы по студиям
    all_exp = pd.concat([d for d in [exp_f, sal_f] if not d.empty], ignore_index=True) if (not exp_f.empty or not sal_f.empty) else pd.DataFrame()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('**Расходы по студиям**')
        if not all_exp.empty:
            exp_by_studio = (
                all_exp[all_exp['studio'].isin(STUDIO_CODES)]
                .groupby('studio')['amount'].sum()
                .reset_index()
            )
            exp_by_studio['studio_name'] = exp_by_studio['studio'].map(STUDIO_CODES)
            exp_by_studio = exp_by_studio.sort_values('amount', ascending=True)
            fig = px.bar(
                exp_by_studio, x='amount', y='studio_name', orientation='h',
                color='amount', color_continuous_scale='Reds',
                labels={'amount': 'Сумма ₽', 'studio_name': ''},
            )
            fig.update_layout(showlegend=False, coloraxis_showscale=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info('Нет данных')

    with col_right:
        st.markdown('**Доходы по студиям**')
        if not rev_f.empty:
            rev_by_studio = (
                rev_f.groupby('studio')['amount'].sum().reset_index()
            )
            rev_by_studio['studio_name'] = rev_by_studio['studio'].map(lambda x: STUDIO_CODES.get(x, x))
            rev_by_studio = rev_by_studio.sort_values('amount', ascending=True)
            fig2 = px.bar(
                rev_by_studio, x='amount', y='studio_name', orientation='h',
                color='amount', color_continuous_scale='Greens',
                labels={'amount': 'Сумма ₽', 'studio_name': ''},
            )
            fig2.update_layout(showlegend=False, coloraxis_showscale=False, height=400)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info('Нет данных')

    # Прибыль по студиям (bar chart)
    st.markdown('**P&L по студиям**')
    if not rev_f.empty and not all_exp.empty:
        rev_s = rev_f.groupby('studio')['amount'].sum()
        exp_s = all_exp[all_exp['studio'].isin(STUDIO_CODES)].groupby('studio')['amount'].sum()
        all_studios_in_data = set(rev_s.index) | set(exp_s.index)
        pnl_rows = []
        for s in all_studios_in_data:
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
    if not exp_f.empty or not sal_f.empty:
        all_exp2 = pd.concat([d for d in [exp_f, sal_f] if not d.empty], ignore_index=True)
        all_exp2['category_name'] = all_exp2['category_code'].map(
            lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else 'Без статьи'
        )
        cat_sum = all_exp2.groupby('category_name')['amount'].sum().reset_index()
        cat_sum = cat_sum.sort_values('amount', ascending=False).head(20)
        cat_sum_asc = cat_sum.sort_values('amount', ascending=True)

        fig4 = px.bar(
            cat_sum_asc, x='amount', y='category_name', orientation='h',
            color='amount', color_continuous_scale='Blues',
            labels={'amount': 'Сумма ₽', 'category_name': ''},
            title='Топ-20 статей расходов',
        )
        fig4.update_layout(height=600, coloraxis_showscale=False)
        st.plotly_chart(fig4, use_container_width=True)

        # Доля в пирог-чарте
        fig5 = px.pie(
            cat_sum, values='amount', names='category_name',
            title='Структура расходов',
        )
        fig5.update_layout(height=500)
        st.plotly_chart(fig5, use_container_width=True)
    else:
        st.info('Нет данных о расходах')


# ══ Вкладка 3: Динамика по месяцам ════════════════════════════════════════════
with tab3:
    def monthly_series(df, label):
        if df is None or df.empty:
            return pd.DataFrame(columns=['month', label])
        mask = (df['year'] == year)
        if studio_filter != 'Все':
            mask &= df['studio'] == studio_filter
        if entity_filter != 'Все':
            mask &= df['entity'] == entity_filter
        s = df[mask].groupby('month')['amount'].sum().reset_index()
        s.columns = ['month', label]
        return s

    rev_monthly = monthly_series(rev_df, 'Доходы')
    exp_monthly = monthly_series(exp_df, 'Расходы')
    sal_monthly = monthly_series(sal_df, 'ЗП')

    # Объединяем
    months_all = pd.DataFrame({'month': list(range(1, 13))})
    merged = months_all.merge(rev_monthly, on='month', how='left')
    merged = merged.merge(exp_monthly, on='month', how='left')
    merged = merged.merge(sal_monthly, on='month', how='left')
    merged = merged.fillna(0)
    merged['Расходы всего'] = merged.get('Расходы', 0) + merged.get('ЗП', 0)
    merged['Прибыль'] = merged['Доходы'] - merged['Расходы всего']
    merged['month_name'] = merged['month'].map(MONTHS_RU)

    fig6 = go.Figure()
    fig6.add_scatter(x=merged['month_name'], y=merged['Доходы'],
                     name='Доходы', line=dict(color='#10B981', width=2.5), mode='lines+markers')
    fig6.add_scatter(x=merged['month_name'], y=merged['Расходы всего'],
                     name='Расходы', line=dict(color='#EF4444', width=2.5), mode='lines+markers')
    fig6.add_scatter(x=merged['month_name'], y=merged['Прибыль'],
                     name='Прибыль', line=dict(color='#3B82F6', width=2, dash='dot'), mode='lines+markers')
    fig6.update_layout(height=400, xaxis_title='', yaxis_title='₽', hovermode='x unified')
    st.plotly_chart(fig6, use_container_width=True)

    # Накопительный итог
    merged['Доходы нарастающим'] = merged['Доходы'].cumsum()
    merged['Расходы нарастающим'] = merged['Расходы всего'].cumsum()
    merged['Прибыль нарастающим'] = merged['Прибыль'].cumsum()

    fig7 = go.Figure()
    fig7.add_scatter(x=merged['month_name'], y=merged['Доходы нарастающим'],
                     name='Доходы YTD', line=dict(color='#10B981'), fill='tonexty')
    fig7.add_scatter(x=merged['month_name'], y=merged['Расходы нарастающим'],
                     name='Расходы YTD', line=dict(color='#EF4444'))
    fig7.update_layout(height=350, title='Накопительный итог (YTD)', xaxis_title='')
    st.plotly_chart(fig7, use_container_width=True)


# ══ Вкладка 4: Сводная таблица ════════════════════════════════════════════════
with tab4:
    st.markdown('**Расходы: статья × студия**')
    if not exp_f.empty or not sal_f.empty:
        all_exp3 = pd.concat([d for d in [exp_f, sal_f] if not d.empty], ignore_index=True)
        all_exp3 = all_exp3[all_exp3['studio'].isin(STUDIO_CODES)]
        all_exp3['category_name'] = all_exp3['category_code'].map(
            lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else 'Без статьи'
        )
        all_exp3['studio_name'] = all_exp3['studio'].map(STUDIO_CODES)

        pivot = all_exp3.pivot_table(
            index='category_name', columns='studio_name',
            values='amount', aggfunc='sum', fill_value=0,
        )
        pivot['ИТОГО'] = pivot.sum(axis=1)
        pivot = pivot.sort_values('ИТОГО', ascending=False)

        # Форматируем числа с пробелом как разделителем тысяч
        fmt_fn = lambda x: f'{x:,.0f}'.replace(',', ' ')
        try:
            styled = pivot.style.format(fmt_fn).background_gradient(
                cmap='Reds', subset=[c for c in pivot.columns if c != 'ИТОГО']
            )
            st.dataframe(styled, use_container_width=True, height=500)
        except Exception:
            # pandas 2.1+ переименовал applymap → map
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
