"""SEO-хелперы: заголовки, описания, JSON-LD разметка."""
import html
import json

from store import BADGE_LABELS


def page_title(shop: str, suffix: str = "") -> str:
    return f"{suffix} — {shop}" if suffix else f"{shop} — интернет-магазин с доставкой"


def meta_description(product: dict, shop: str) -> str:
    text = (product.get("description") or "").strip()
    if len(text) > 40:
        base = text[:130].rsplit(" ", 1)[0]
    else:
        base = text or f"{product['name']} с доставкой"
    return f"{base} — купить в {shop} за {product['price']} ₽. Быстрая доставка по всей стране."


def clean(text: str, limit: int) -> str:
    return html.escape(" ".join((text or "").split())[:limit])


def article_jsonld(post: dict, shop: str, url: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post["title"],
        "description": (post.get("excerpt") or "")[:200],
        "publisher": {"@type": "Organization", "name": shop},
        "mainEntityOfPage": url,
        "datePublished": (post.get("created_at") or "")[:10],
    }
    if post.get("cover"):
        data["image"] = [post["cover"]]
    return json.dumps(data, ensure_ascii=False)


_CONDITION_SCHEMA = {"new": "https://schema.org/NewCondition",
                     "used": "https://schema.org/UsedCondition",
                     "defect": "https://schema.org/DamagedCondition"}

def product_jsonld(product: dict, shop: str, url: str, review_stats: dict = None) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product["name"],
        "image": [url.rsplit("/", 1)[0] + product["photo"] if product["photo"].startswith("/") else product["photo"]],
        "description": (product.get("description") or "")[:300],
        "sku": product.get("code") or f"TG-{product['id']}",
        "brand": {"@type": "Brand", "name": shop},
        "offers": {
            "@type": "Offer",
            "url": url,
            "priceCurrency": "RUB",
            "price": str(product["price"]),
            "availability": "https://schema.org/InStock" if product.get("in_stock") else "https://schema.org/OutOfStock",
            "seller": {"@type": "Organization", "name": shop},
            "itemCondition": _CONDITION_SCHEMA.get(product.get("condition"), _CONDITION_SCHEMA["new"]),
        },
    }
    if product.get("subcategory"):
        data["category"] = product["subcategory"]
    brand = ((product.get("params") or {}).get("Бренд") or "").strip()
    if brand:
        data["brand"] = {"@type": "Brand", "name": brand}
    params = product.get("params") or {}
    if params:
        data["additionalProperty"] = [
            {"@type": "PropertyValue", "name": str(k), "value": str(v)}
            for k, v in params.items() if str(v).strip()
        ]
    if review_stats and review_stats.get("count"):
        data["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": str(review_stats["avg"]),
            "reviewCount": str(review_stats["count"]),
            "bestRating": "5",
            "worstRating": "1",
        }
    return json.dumps(data, ensure_ascii=False)


def faq_jsonld(items: list, url: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q.get("q", "")[:200],
                "acceptedAnswer": {"@type": "Answer", "text": q.get("a", "")[:500]},
            }
            for q in items if q.get("q")
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def org_jsonld(shop: str, url: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "OnlineStore",
        "name": shop,
        "url": url,
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint", "urlTemplate": url + "catalog?q={search_term_string}"},
            "query-input": "required name=search_term_string",
        },
    }
    return json.dumps(data, ensure_ascii=False)


def breadcrumbs_jsonld(items: list, url: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": link}
            for i, (name, link) in enumerate(items)
        ],
    }
    return json.dumps(data, ensure_ascii=False)
