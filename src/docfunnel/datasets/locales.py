"""Locales shared by both synthetic generators: currency, number and date formats,
tax vocabulary, vendors and line items for US, UK, DE and BR documents."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from docfunnel.extract.schema import PaymentMethod

D = Decimal


@dataclass(frozen=True)
class Locale:
    code: str
    currency: str
    symbol: str
    decimal_comma: bool
    symbol_after: bool
    date_formats: tuple[str, ...]
    labels: dict[str, str]
    tax_rates: tuple[Decimal, ...]
    payments: tuple[tuple[str, PaymentMethod], ...]
    vendors: tuple[str, ...]
    customers: tuple[str, ...]
    pos_items: tuple[tuple[str, Decimal], ...]
    invoice_items: tuple[tuple[str, Decimal], ...]
    tax_id: Callable[[random.Random], str]
    addresses: tuple[str, ...]
    pos_tax_probability: float = 1.0


def digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


LOCALES: dict[str, Locale] = {
    "us": Locale(
        code="us",
        currency="USD",
        symbol="$",
        decimal_comma=False,
        symbol_after=False,
        date_formats=("%m/%d/%Y", "%b %d, %Y", "%Y-%m-%d"),
        labels={
            "subtotal": "Subtotal",
            "tax": "Sales Tax ({rate}%)",
            "total": "TOTAL",
            "invoice_total": "Total due (USD)",
            "date": "Date:",
            "receipt_no": "Receipt #",
            "invoice": "INVOICE",
            "invoice_no": "Invoice No:",
            "invoice_date": "Invoice Date:",
            "tax_id": "EIN:",
            "payment": "Paid by:",
            "thanks": "Thank you for shopping!",
            "bill_to": "Bill to:",
            "header": "Description | Qty | Unit Price | Amount",
        },
        tax_rates=(D("0.06"), D("0.0725"), D("0.08"), D("0.0875")),
        payments=(
            ("VISA ****{d4}", PaymentMethod.CARD),
            ("MASTERCARD ****{d4}", PaymentMethod.CARD),
            ("CASH", PaymentMethod.CASH),
            ("Wire transfer", PaymentMethod.BANK_TRANSFER),
        ),
        vendors=(
            "Blue Harbor Coffee",
            "Maple Street Hardware",
            "Sunrise Deli & Bakery",
            "Pinecrest Books",
            "Lakeside Pharmacy",
            "Copper Kettle Diner",
        ),
        customers=("Contoso Ltd", "Fabrikam Inc", "Northbridge Analytics LLC"),
        pos_items=(
            ("Latte", D("4.50")),
            ("Bagel w/ Cream Cheese", D("3.25")),
            ("Hammer 16oz", D("18.99")),
            ("Wood Screws 100pk", D("7.49")),
            ("Paperback Novel", D("14.99")),
            ("Notebook A5", D("5.99")),
            ("Vitamin C 500mg", D("9.99")),
            ("Club Sandwich", D("11.50")),
            ("Iced Tea", D("2.75")),
            ("Batteries AA 8pk", D("8.99")),
        ),
        invoice_items=(
            ("Consulting (hours)", D("125.00")),
            ("Data pipeline audit", D("1450.00")),
            ("Cloud hosting - monthly", D("89.00")),
            ("Training workshop", D("600.00")),
        ),
        tax_id=lambda rng: f"{digits(rng, 2)}-{digits(rng, 7)}",
        addresses=(
            "123 Ocean Ave, Portland, OR 97201",
            "48 Maple St, Burlington, VT 05401",
            "910 Elm Rd, Austin, TX 78701",
        ),
        pos_tax_probability=0.8,
    ),
    "uk": Locale(
        code="uk",
        currency="GBP",
        symbol="£",
        decimal_comma=False,
        symbol_after=False,
        date_formats=("%d/%m/%Y", "%d %b %Y"),
        labels={
            "subtotal": "Net",
            "tax": "VAT {rate}%",
            "total": "Total",
            "invoice_total": "Amount due (GBP)",
            "date": "Date",
            "receipt_no": "Till receipt no.",
            "invoice": "TAX INVOICE",
            "invoice_no": "Invoice number:",
            "invoice_date": "Invoice date:",
            "tax_id": "VAT Reg No:",
            "payment": "Payment:",
            "thanks": "Thank you, please come again",
            "bill_to": "Invoice to:",
            "header": "Item | Qty | Unit | Line total",
        },
        tax_rates=(D("0.20"),),
        payments=(
            ("Card", PaymentMethod.CARD),
            ("Contactless VISA", PaymentMethod.CARD),
            ("Cash", PaymentMethod.CASH),
            ("BACS transfer", PaymentMethod.BANK_TRANSFER),
        ),
        vendors=(
            "Northwind Office Supply Ltd",
            "The Crown & Anchor",
            "Riverside Garden Centre",
            "Hollybush Stationers",
        ),
        customers=("Tailspin Toys Ltd", "Wingtip Partners LLP"),
        pos_items=(
            ("A4 Paper Ream", D("4.20")),
            ("Pint of Bitter", D("4.80")),
            ("Fish & Chips", D("12.50")),
            ("Compost 40L", D("6.99")),
            ("Ballpoint Pens x10", D("3.49")),
            ("Desk Lamp", D("24.00")),
        ),
        invoice_items=(
            ("Support retainer", D("450.00")),
            ("Toner Cartridge", D("39.90")),
            ("On-site visit", D("180.00")),
            ("Office chairs", D("129.00")),
        ),
        tax_id=lambda rng: f"GB {digits(rng, 3)} {digits(rng, 4)} {digits(rng, 2)}",
        addresses=("14 High Street, Oxford OX1 4AA", "2 Quay Lane, Bristol BS1 5DS"),
    ),
    "de": Locale(
        code="de",
        currency="EUR",
        symbol="€",
        decimal_comma=True,
        symbol_after=True,
        date_formats=("%d.%m.%Y",),
        labels={
            "subtotal": "Zwischensumme",
            "tax": "MwSt {rate}%",
            "total": "SUMME",
            "invoice_total": "Gesamtbetrag (EUR)",
            "date": "Datum:",
            "receipt_no": "Bon-Nr.",
            "invoice": "RECHNUNG",
            "invoice_no": "Rechnung Nr.",
            "invoice_date": "Rechnungsdatum:",
            "tax_id": "USt-IdNr.:",
            "payment": "Zahlung:",
            "thanks": "Vielen Dank für Ihren Einkauf",
            "bill_to": "Kunde:",
            "header": "Artikel | Menge | Einzelpreis | Betrag",
        },
        tax_rates=(D("0.19"), D("0.07")),
        payments=(
            ("Bar", PaymentMethod.CASH),
            ("EC-Karte", PaymentMethod.CARD),
            ("Kreditkarte", PaymentMethod.CARD),
            ("Überweisung", PaymentMethod.BANK_TRANSFER),
        ),
        vendors=(
            "Bäckerei Sonnenschein",
            "Elektro Krüger GmbH",
            "Buchhandlung am Markt",
            "Café Lindenblatt",
        ),
        customers=("Musterfirma AG", "Beispiel & Söhne KG"),
        pos_items=(
            ("Roggenbrot", D("3.40")),
            ("Brezel", D("0.95")),
            ("Cappuccino", D("3.20")),
            ("USB-C Kabel", D("12.99")),
            ("LED Lampe E27", D("7.49")),
            ("Taschenbuch", D("11.00")),
            ("Apfelstrudel", D("4.10")),
        ),
        invoice_items=(
            ("Beratung (Std.)", D("95.00")),
            ("Wartungsvertrag", D("1200.00")),
            ("Installation", D("240.00")),
        ),
        tax_id=lambda rng: f"DE{digits(rng, 9)}",
        addresses=("Marktplatz 3, 79098 Freiburg", "Hauptstraße 21, 10115 Berlin"),
    ),
    "br": Locale(
        code="br",
        currency="BRL",
        symbol="R$",
        decimal_comma=True,
        symbol_after=False,
        date_formats=("%d/%m/%Y",),
        labels={
            "subtotal": "Subtotal",
            "tax": "ISS {rate}%",
            "total": "TOTAL",
            "invoice_total": "Valor total (BRL)",
            "date": "Data:",
            "receipt_no": "Cupom nº",
            "invoice": "NOTA FISCAL DE SERVIÇO",
            "invoice_no": "Nota nº",
            "invoice_date": "Data de emissão:",
            "tax_id": "CNPJ:",
            "payment": "Pagamento:",
            "thanks": "Obrigado pela preferência!",
            "bill_to": "Tomador:",
            "header": "Descrição | Qtd | Valor unit. | Valor",
        },
        tax_rates=(D("0.05"), D("0.02")),
        payments=(
            ("Pix", PaymentMethod.PIX),
            ("Cartão de crédito", PaymentMethod.CARD),
            ("Cartão de débito", PaymentMethod.CARD),
            ("Dinheiro", PaymentMethod.CASH),
        ),
        vendors=(
            "Padaria Pão Dourado",
            "Farmácia Boa Saúde",
            "Mercadinho Vila Nova",
            "Papelaria Estrela",
        ),
        customers=("Exemplo Tecnologia Ltda", "Comércio Fictício S.A."),
        pos_items=(
            ("Pão francês kg", D("15.90")),
            ("Café expresso", D("6.50")),
            ("Dipirona 500mg", D("8.79")),
            ("Caderno 96 fls", D("18.90")),
            ("Leite integral 1L", D("5.49")),
            ("Queijo minas kg", D("42.90")),
        ),
        invoice_items=(
            ("Serviço de manutenção", D("380.00")),
            ("Consultoria (horas)", D("150.00")),
            ("Licença de software", D("1890.00")),
        ),
        tax_id=lambda rng: (
            f"{digits(rng, 2)}.{digits(rng, 3)}.{digits(rng, 3)}/0001-{digits(rng, 2)}"
        ),
        addresses=("Rua das Flores, 120 - Niterói/RJ", "Av. Paulista, 1000 - São Paulo/SP"),
        pos_tax_probability=0.0,  # retail receipts here carry no separate tax line
    ),
}


def format_amount(amount: Decimal, locale: Locale, *, symbol: bool = True) -> str:
    text = f"{amount:,.2f}"
    if locale.decimal_comma:
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    if not symbol:
        return text
    return (
        f"{text} {locale.symbol}"
        if locale.symbol_after
        else (f"{locale.symbol} {text}" if len(locale.symbol) > 1 else f"{locale.symbol}{text}")
    )
