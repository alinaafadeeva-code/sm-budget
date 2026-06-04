import streamlit as st


def check_password() -> bool:
    """
    Показывает экран входа и проверяет пароль.
    Возвращает True если пользователь авторизован.
    Пароль хранится в st.secrets['app_password'].
    """

    # Уже вошли в этой сессии
    if st.session_state.get('_authenticated'):
        return True

    # Пароль не настроен — пропускаем (для локальной разработки)
    if 'app_password' not in st.secrets:
        st.session_state['_authenticated'] = True
        return True

    # ── Экран входа ───────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    .login-wrap {
        max-width: 380px; margin: 80px auto 0; padding: 40px 36px;
        background: white; border-radius: 18px;
        box-shadow: 0 4px 24px rgba(0,0,0,.10);
        text-align: center;
    }
    .login-logo { font-size: 48px; margin-bottom: 8px; }
    .login-title { font-size: 22px; font-weight: 800; color: #1F2937;
                   margin-bottom: 4px; }
    .login-sub   { font-size: 14px; color: #6B7280; margin-bottom: 28px; }
    </style>
    <div class="login-wrap">
        <div class="login-logo">💪</div>
        <div class="login-title">SM Stretching</div>
        <div class="login-sub">Финансовый дашборд</div>
    </div>
    """, unsafe_allow_html=True)

    # Форма ввода
    with st.form('login_form', clear_on_submit=True):
        pwd = st.text_input('Пароль', type='password', placeholder='Введи пароль...')
        submitted = st.form_submit_button('Войти', use_container_width=True, type='primary')

    if submitted:
        if pwd == st.secrets['app_password']:
            st.session_state['_authenticated'] = True
            st.rerun()
        else:
            st.error('Неверный пароль. Попробуй ещё раз.')

    return False


def logout():
    """Выход из системы."""
    st.session_state['_authenticated'] = False
    st.rerun()


def show_logout_button():
    """Кнопка выхода в сайдбаре."""
    with st.sidebar:
        st.divider()
        if st.button('🚪 Выйти', use_container_width=True):
            logout()
