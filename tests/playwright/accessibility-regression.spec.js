const { test, expect } = require('@playwright/test');
const baseURL = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173';
const surfaces = [
  { name: 'home', path: '/', ready: '#hero-title' },
  { name: 'internal training', path: '/internal', ready: '#internal-training-title' },
  { name: 'PGY', path: '/pgy', ready: 'main' },
  { name: 'learning/admin workspace', path: '/system?area=internal&group=grpBio&module=materials', ready: '#module-hub-heading' },
];
async function open(page, surface, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(`${baseURL}${surface.path}`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator(surface.ready).first()).toBeVisible({ timeout: 10000 });
  await page.waitForTimeout(250);
}
async function auditDom(page) {
  return page.evaluate(() => {
    const violations = [];
    const describe = el => {
      if (!el) return '<missing>';
      const id = el.id ? `#${el.id}` : '';
      const cls = typeof el.className === 'string' && el.className.trim() ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}` : '';
      return `${el.tagName.toLowerCase()}${id}${cls}`;
    };
    const isVisible = el => {
      if (!(el instanceof Element)) return false;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse' || Number(style.opacity) === 0) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const labelledByText = el => String(el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
    const labelText = el => {
      if (el.id) {
        const explicit = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (explicit) return explicit.textContent.trim();
      }
      return el.closest('label')?.textContent?.trim() || '';
    };
    const accessibleName = el => String(el.getAttribute('aria-label') || labelledByText(el) || labelText(el) || el.getAttribute('title') || el.getAttribute('alt') || el.textContent || el.getAttribute('value') || '').replace(/\s+/g, ' ').trim();
    if (!String(document.documentElement.lang || '').trim()) violations.push('document: missing html[lang]');
    const mains = Array.from(document.querySelectorAll('main')).filter(isVisible);
    if (mains.length !== 1) violations.push(`landmark: expected one visible main, found ${mains.length}`);
    const ids = new Map();
    document.querySelectorAll('[id]').forEach(el => ids.set(el.id, (ids.get(el.id) || 0) + 1));
    for (const [id, count] of ids.entries()) if (count > 1) violations.push(`id: duplicate #${id} (${count})`);
    document.querySelectorAll('img').forEach(img => { if (!img.hasAttribute('alt')) violations.push(`image: ${describe(img)} missing alt attribute`); });
    document.querySelectorAll('[tabindex]').forEach(el => {
      const value = Number(el.getAttribute('tabindex'));
      if (Number.isFinite(value) && value > 0) violations.push(`keyboard: ${describe(el)} uses positive tabindex=${value}`);
    });
    document.querySelectorAll('a[href],button,summary,[role="button"],input:not([type="hidden"]),select,textarea').forEach(el => {
      if (!isVisible(el) || el.matches('[disabled],[aria-disabled="true"]')) return;
      if (!accessibleName(el)) violations.push(`name: ${describe(el)} has no accessible name`);
    });
    const navs = Array.from(document.querySelectorAll('nav')).filter(isVisible);
    if (navs.length > 1) navs.forEach(nav => {
      if (!String(nav.getAttribute('aria-label') || labelledByText(nav)).trim()) violations.push(`landmark: ${describe(nav)} needs a label because multiple nav landmarks are visible`);
    });
    document.querySelectorAll('[aria-hidden="true"]').forEach(root => {
      if (!isVisible(root)) return;
      const focusable = Array.from(root.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]')).find(el => isVisible(el) && el.getAttribute('tabindex') !== '-1');
      if (focusable) violations.push(`aria-hidden: ${describe(root)} contains focusable ${describe(focusable)}`);
    });
    document.querySelectorAll('dialog').forEach(dialog => {
      if (!String(dialog.getAttribute('aria-label') || labelledByText(dialog)).trim()) violations.push(`dialog: ${describe(dialog)} has no accessible name`);
    });
    const viewport = window.innerWidth;
    const documentWidth = document.documentElement.scrollWidth;
    const bodyWidth = document.body.scrollWidth;
    if (documentWidth > viewport + 2 || bodyWidth > viewport + 2) violations.push(`layout: horizontal overflow viewport=${viewport} document=${documentWidth} body=${bodyWidth}`);
    return violations;
  });
}
for (const viewport of [{ name: 'mobile', width: 390, height: 844 }, { name: 'desktop', width: 1440, height: 1000 }]) {
  for (const surface of surfaces) {
    test(`${surface.name} passes WCAG guard on ${viewport.name}`, async ({ page }) => {
      await open(page, surface, viewport);
      const violations = await auditDom(page);
      expect(violations, violations.join('\n')).toEqual([]);
    });
  }
}
test('keyboard focus remains visible on learner portal navigation', async ({ page }) => {
  await open(page, surfaces[0], { width: 1440, height: 1000 });
  for (let step = 0; step < 6; step += 1) {
    await page.keyboard.press('Tab');
    const focus = await page.evaluate(() => {
      const el = document.activeElement;
      const style = getComputedStyle(el);
      return { tag: el?.tagName || '', outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow };
    });
    expect(focus.tag).not.toBe('BODY');
    const outlineWidth = Number.parseFloat(focus.outlineWidth || '0');
    expect((focus.outlineStyle !== 'none' && outlineWidth > 0) || focus.boxShadow !== 'none', JSON.stringify(focus)).toBeTruthy();
  }
});
test('profile dialog is keyboard-operable, named and owns focus while open', async ({ page }) => {
  await open(page, surfaces[0], { width: 1440, height: 1000 });
  const trigger = page.locator('#v561-profile-trigger');
  await trigger.focus();
  await page.keyboard.press('Enter');
  const dialog = page.locator('#v561-profile-dialog');
  await expect(dialog).toHaveAttribute('aria-label', /.+/);
  await expect(dialog).toHaveJSProperty('open', true);
  expect(await page.evaluate(() => {
    const dialog = document.getElementById('v561-profile-dialog');
    return Boolean(dialog && dialog.contains(document.activeElement));
  })).toBeTruthy();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveJSProperty('open', false);
});
