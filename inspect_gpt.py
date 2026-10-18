"""Debug : inspecte le champ de saisie de ChatGPT (non connecté) et teste un envoi."""
from llm_browser import Browser, _dismiss_banners

with Browser("browser_profile") as b:
    page = b.ctx.new_page()
    page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    _dismiss_banners(page)
    print(page.evaluate("""() => [...document.querySelectorAll('textarea, [contenteditable], [role=textbox]')].map(e =>
        e.tagName + ' id=' + e.id + ' class=' + e.className + ' ce=' + e.getAttribute('contenteditable') +
        ' role=' + e.getAttribute('role') + ' ph=' + (e.getAttribute('placeholder')||e.getAttribute('data-placeholder')||'') +
        ' vis=' + (e.offsetParent !== null))"""))
    box = page.get_by_role("textbox").first
    box.click()
    page.keyboard.insert_text("Traduis en francais: Hello world. Reponds dans un bloc de code ```html puis <!--FIN-->")
    page.keyboard.press("Enter")
    page.wait_for_timeout(25000)
    print("code blocks:", page.locator("pre code").count())
    print(page.inner_text("body")[-600:].replace("\n", " | "))
