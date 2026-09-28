"""Extract the main document without menus, cookie banners or site footers."""
from bs4 import BeautifulSoup


def document_text(body: bytes) -> str:
    soup = BeautifulSoup(body, 'html.parser')
    for item in soup.select('script,style,noscript,svg,nav,footer,[role="navigation"],.gem-c-cookie-banner,.govuk-cookie-banner,.cookie-banner'):
        item.decompose()
    main = soup.select_one('main,article,[role="main"],#main-content,.govuk-govspeak,.TRS_Editor')
    return ' '.join((main or soup).get_text(' ', strip=True).split())
