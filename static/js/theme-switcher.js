/**
 * Theme Switcher - Gerenciador de Temas do Caixô
 * 
 * Gerencia a persistência e aplicação de temas (Claro, Escuro, Sistema)
 * usando localStorage e prefers-color-scheme.
 * 
 * Funcionalidades:
 * - Detecta preferência do sistema operacional
 * - Persiste escolha do usuário no localStorage
 * - Aplica classe 'dark' no elemento <html> para Tailwind CSS
 * - Atualiza botões de seleção visualmente
 */

(function() {
    'use strict';
    
    // Chave para armazenar no localStorage
    const THEME_STORAGE_KEY = 'caixo-theme';
    
    // Valores possíveis de tema
    const THEMES = {
        LIGHT: 'light',
        DARK: 'dark',
        SYSTEM: 'system'
    };
    
    /**
     * Obtém o tema salvo no localStorage ou retorna 'system' como padrão.
     * 
     * @returns {string} Tema salvo ou 'system'
     */
    function getSavedTheme() {
        try {
            const saved = localStorage.getItem(THEME_STORAGE_KEY);
            return saved && Object.values(THEMES).includes(saved) ? saved : THEMES.SYSTEM;
        } catch (e) {
            console.warn('Erro ao ler tema do localStorage:', e);
            return THEMES.SYSTEM;
        }
    }
    
    /**
     * Salva o tema no localStorage.
     * 
     * @param {string} theme - Tema a ser salvo
     */
    function saveTheme(theme) {
        try {
            localStorage.setItem(THEME_STORAGE_KEY, theme);
        } catch (e) {
            console.warn('Erro ao salvar tema no localStorage:', e);
        }
    }
    
    /**
     * Detecta se o sistema operacional está em modo escuro.
     * 
     * @returns {boolean} True se o sistema está em modo escuro
     */
    function isSystemDark() {
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    
    /**
     * Aplica o tema no DOM adicionando ou removendo a classe 'dark' no <html>.
     * 
     * @param {string} theme - Tema a ser aplicado ('light', 'dark' ou 'system')
     */
    function applyTheme(theme) {
        const html = document.documentElement;
        
        // Remove classe 'dark' se existir
        html.classList.remove('dark');
        
        // Determina se deve aplicar modo escuro
        let shouldBeDark = false;
        
        if (theme === THEMES.DARK) {
            shouldBeDark = true;
        } else if (theme === THEMES.SYSTEM) {
            shouldBeDark = isSystemDark();
        }
        // Se theme === 'light', shouldBeDark permanece false
        
        // Aplica ou remove a classe 'dark'
        if (shouldBeDark) {
            html.classList.add('dark');
        }
    }
    
    /**
     * Atualiza o estado visual dos botões de tema na página de configurações.
     */
    function updateThemeButtons() {
        const currentTheme = getSavedTheme();
        
        // Remove estilo ativo de todos os botões
        const buttons = ['theme-light', 'theme-dark', 'theme-system'];
        buttons.forEach(buttonId => {
            const button = document.getElementById(buttonId);
            if (button) {
                button.style.borderColor = '#E9E4DB';
                button.style.color = '#2D2926';
                button.style.backgroundColor = '#FFFFFF';
            }
        });
        
        // Aplica estilo ativo ao botão do tema atual
        const activeButton = document.getElementById('theme-' + currentTheme);
        if (activeButton) {
            activeButton.style.borderColor = '#D4AF37';
            activeButton.style.color = '#FFFFFF';
            activeButton.style.backgroundColor = '#D4AF37';
        }
    }
    
    /**
     * Define o tema e aplica imediatamente.
     * 
     * @param {string} theme - Tema a ser definido
     */
    function setTheme(theme) {
        if (!Object.values(THEMES).includes(theme)) {
            console.warn('Tema inválido:', theme);
            return;
        }
        
        // Salva no localStorage
        saveTheme(theme);
        
        // Aplica no DOM
        applyTheme(theme);
        
        // Atualiza botões (se estiver na página de configurações)
        updateThemeButtons();
    }
    
    /**
     * Inicializa listeners e funcionalidades do tema.
     * O tema já foi aplicado pelo script inline no <head>, então aqui apenas
     * configuramos os listeners para mudanças futuras.
     */
    function initThemeListeners() {
        // Listener para mudanças na preferência do sistema (quando tema = 'system')
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addEventListener('change', function(e) {
                const currentTheme = getSavedTheme();
                if (currentTheme === THEMES.SYSTEM) {
                    applyTheme(THEMES.SYSTEM);
                }
            });
        }
        
        // Atualiza botões de tema se estiver na página de configurações
        updateThemeButtons();
    }
    
    // Expõe funções globalmente IMEDIATAMENTE (antes do DOM estar pronto)
    // Isso garante que os botões onclick possam chamar as funções
    window.setTheme = setTheme;
    window.updateThemeButtons = updateThemeButtons;
    window.getSavedTheme = getSavedTheme;
    
    // Inicializa listeners quando o DOM estiver pronto
    // O tema já foi aplicado pelo script inline no <head>
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initThemeListeners);
    } else {
        // Se o DOM já estiver pronto, executa imediatamente
        initThemeListeners();
    }
})();
