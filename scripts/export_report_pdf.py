"""Optional PDF export for a self-contained HTML report (Playwright + Chromium)."""
import argparse
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html',type=Path)
    parser.add_argument('pdf',type=Path)
    parser.add_argument('--chromium',default=shutil.which('chromium') or shutil.which('google-chrome'))
    parser.add_argument('--base-url',help='Published directory URL used to resolve evidence links in the PDF.')
    args=parser.parse_args()
    if args.pdf.exists():
        parser.error('Output already exists; preserve prior reports and choose a new file.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        parser.error('Optional export requires Playwright and a Chromium installation.')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        page=browser.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_content(args.html.read_text(encoding='utf8'),wait_until='load')
        if args.base_url:
            page.evaluate('(url)=>{const base=document.createElement("base");base.href=url;document.head.prepend(base)}',args.base_url)
        if not page.locator('h1').count():
            raise ValueError('Report has no title')
        if not page.locator('img').evaluate_all('(images)=>images.every(i=>i.complete&&i.naturalWidth>0)'):
            raise ValueError('An embedded report image failed to load')
        if errors:
            raise ValueError(f'Browser errors: {errors}')
        args.pdf.parent.mkdir(parents=True,exist_ok=True)
        page.pdf(path=str(args.pdf),format='A4',print_background=True,
                 margin={'top':'13mm','bottom':'16mm','left':'12mm','right':'12mm'},
                 display_header_footer=True,header_template='<div></div>',
                 footer_template='<div style="width:100%;text-align:center;font-size:8px;color:#555">Apuração presidencial · análise geográfica · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        browser.close()
    print(args.pdf)


if __name__=='__main__':
    main()
