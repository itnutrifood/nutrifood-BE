# Email templates

Customer email layouts and translations live here. `order_confirmation.html` is the shared
HTML layout; `locales/en.json`, `locales/hy.json`, and `locales/ru.json` contain all customer-facing
copy, including subject lines and month names. Keep the same keys in all three files. The
renderer also builds a plain-text version from the same translations.

Checkout accepts `X-Locale: en|hy|ru` for the language selected on the website. If it is absent,
the API uses the best supported `Accept-Language` value, then English. The resolved language is
passed with the queued email job. Existing jobs without a language still render in English.

The `{number}`, `{total}`, and `{name}` placeholders in the translation files are filled by the
renderer. Customer and catalog values are escaped before insertion into HTML.

Order emails show the first current product image as a small thumbnail for each line item. Images
use public HTTPS URLs; the email still shows the product name and prices when an image is missing
or the mail client blocks remote images.
