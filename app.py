from dukaan_saathi.ui.gradio_app import CUSTOM_CSS, THEME, build_demo


demo = build_demo()

if __name__ == "__main__":
    demo.launch(css=CUSTOM_CSS, theme=THEME)
