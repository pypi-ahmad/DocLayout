"""Estimated USD costs using user-supplied rates and reported API usage."""

from decimal import Decimal

# USD per million tokens: ordinary input, cached input, cache writes, output.
MODEL_RATES = {
    "gpt-6-sol": ("2.00", "0.20", "2.50", "10.00"),
    "gpt-6-luna": ("0.10", "0.01", "0.125", "0.50"),
}


def token_count(value):
    return value if type(value) is int and value >= 0 else None


def response_usage(usage, model):
    def field(obj, name, default=None):
        return (
            obj.get(name, default)
            if isinstance(obj, dict)
            else getattr(obj, name, default)
        )

    inp = token_count(field(usage, "input_tokens"))
    out = token_count(field(usage, "output_tokens"))
    details = field(usage, "input_tokens_details")
    return {
        "model": model,
        "known": inp is not None and out is not None,
        "tokens": {
            "input_tokens": inp,
            "output_tokens": out,
            "input_token_details": {
                "cache_read": token_count(field(details, "cached_tokens")),
                "cache_write": token_count(field(details, "cache_write_tokens")),
            },
        },
    }


def cost_summary(entries):
    """Price reported requests; unknown calls make the subtotal incomplete."""
    cost = Decimal(0)
    totals = dict(
        input_tokens=0, output_tokens=0, cached_tokens=0, cache_write_tokens=0
    )
    unknown = 0
    for entry in entries:
        tokens = entry.get("tokens") or {}
        inp = token_count(tokens.get("input_tokens"))
        out = token_count(tokens.get("output_tokens"))
        details = tokens.get("input_token_details") or {}
        cached = token_count(details.get("cache_read")) or 0
        writes = token_count(details.get("cache_write")) or 0
        rates = MODEL_RATES.get(entry.get("model"))
        if (
            not entry.get("known")
            or inp is None
            or out is None
            or rates is None
            or cached + writes > inp
        ):
            unknown += 1
            continue
        counts = (inp - cached - writes, cached, writes, out)
        cost += sum(
            Decimal(count) * Decimal(rate) for count, rate in zip(counts, rates)
        ) / Decimal(1_000_000)
        for key, count in zip(totals, (inp, out, cached, writes)):
            totals[key] += count
    return {
        "estimated_cost_usd": float(cost),
        "complete": unknown == 0,
        "requests": len(entries),
        "unknown_requests": unknown,
        **totals,
    }


def cost_message(entries):
    summary = cost_summary(entries)
    suffix = (
        f" (partial; {summary['unknown_requests']} request(s) without usable usage)"
        if not summary["complete"]
        else ""
    )
    return f"Estimated API cost: ${summary['estimated_cost_usd']:.6f}{suffix}"
