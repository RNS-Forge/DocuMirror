"""
Pydantic schemas for the three supported document types.
Each schema captures both field values and layout metadata needed
to reconstruct a faithful EJS template.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class Alignment(str, Enum):
    left = "left"
    center = "center"
    right = "right"


class LayoutMeta(BaseModel):
    """Visual/structural metadata extracted by the vision LLM for one page."""

    page_width_px: Optional[int] = Field(None, description="Page width in pixels at render DPI")
    page_height_px: Optional[int] = Field(None, description="Page height in pixels at render DPI")
    has_border: bool = Field(False, description="Whether the document has an outer border/box")
    header_bg_color: Optional[str] = Field(None, description="Hex color of the document header area, e.g. '#003087'")
    font_family: Optional[str] = Field(None, description="Dominant font family detected, e.g. 'Arial'")
    font_size_body: Optional[str] = Field(None, description="Body font size, e.g. '10px'")
    table_border_style: Optional[str] = Field(None, description="CSS border style for tables, e.g. '1px solid #000'")
    column_alignments: Optional[List[Alignment]] = Field(None, description="Per-column alignment for the main item table")
    bold_labels: bool = Field(True, description="Whether field labels are bold")
    two_column_layout: bool = Field(False, description="Whether header section uses two-column label/value grid")

    # ------------------------------------------------------------------
    # Coerce numeric sizes to CSS strings and tolerate unexpected types
    # ------------------------------------------------------------------

    @field_validator("font_size_body", mode="before")
    @classmethod
    def _coerce_font_size(cls, v: Any) -> Optional[str]:
        """Accept int/float from LLM (e.g. 10) and turn into '10px'."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return f"{int(v)}px"
        return str(v)

    @field_validator("font_family", "header_bg_color", "table_border_style", mode="before")
    @classmethod
    def _coerce_to_str(cls, v: Any) -> Optional[str]:
        """Coerce any non-None value to string so int/bool from LLM doesn't blow up."""
        if v is None:
            return None
        return str(v)

    @field_validator("has_border", "bold_labels", "two_column_layout", mode="before")
    @classmethod
    def _coerce_bool(cls, v: Any) -> bool:
        """Accept string booleans ('true'/'false') from LLM responses."""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    @field_validator("page_width_px", "page_height_px", mode="before")
    @classmethod
    def _coerce_int(cls, v: Any) -> Optional[int]:
        """Silently drop non-numeric values for pixel dimensions."""
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @field_validator("column_alignments", mode="before")
    @classmethod
    def _coerce_alignments(cls, v: Any) -> Optional[List[str]]:
        """Accept a list of strings or a single string; ignore unrecognised values."""
        if v is None:
            return None
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            valid = {"left", "center", "right"}
            return [item for item in v if isinstance(item, str) and item.lower() in valid] or None
        return None


# ---------------------------------------------------------------------------
# Commercial Invoice
# ---------------------------------------------------------------------------

class BankDetails(BaseModel):
    model_config = {"extra": "ignore"}

    account_name: Optional[str] = None
    bank_name: Optional[str] = None
    account_no: Optional[str] = None
    swift_code: Optional[str] = None
    iban: Optional[str] = None
    branch: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_all_to_str(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        return {k: str(v) if v is not None and not isinstance(v, str) else v
                for k, v in values.items()}


class CommercialInvoiceItem(BaseModel):
    model_config = {"extra": "ignore"}

    sr_no: Optional[str] = None
    description: str = Field(default="", description="Product/goods description")
    hs_code: Optional[str] = Field(None, description="Harmonized System tariff code")
    hsn_code: Optional[str] = Field(None, description="HSN Code")
    style_name: Optional[str] = Field(None, description="Style Name")
    style_no: Optional[str] = Field(None, description="Style No")
    size: Optional[str] = Field(None, description="Size")
    article_no: Optional[str] = Field(None, description="Article No")
    colour: Optional[str] = Field(None, description="Colour")
    qty: str = Field(default="", description="Quantity with unit, e.g. '100 PCS'")
    unit_price: str = Field(default="", description="Price per unit with currency, e.g. 'USD 5.00'")
    amount: str = Field(default="", description="Line total, e.g. 'USD 500.00'")

    @model_validator(mode="before")
    @classmethod
    def _coerce_all_to_str(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        return {k: str(v) if v is not None and not isinstance(v, str) else v
                for k, v in values.items()}


class CommercialInvoice(BaseModel):
    """Schema for a commercial invoice document."""
    model_config = {"extra": "ignore"}

    doc_type: str = Field("commercial_invoice", description="Fixed identifier for template selection")

    # Parties
    exporter: Optional[str] = Field(None, description="Exporter name and address (multiline)")
    importer: Optional[str] = Field(None, description="Importer / consignee name and address (multiline)")
    notify_party: Optional[str] = None

    # Reference numbers
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = None
    iec_no: Optional[str] = Field(None, description="Importer Exporter Code")
    gst_no: Optional[str] = Field(None, description="GST / VAT registration number")
    po_no: Optional[str] = Field(None, description="Buyer purchase order number")
    lc_no: Optional[str] = Field(None, description="Letter of Credit number, if any")
    lut_arn: Optional[str] = Field(None, description="LUT ARN details")
    lut_date: Optional[str] = Field(None, description="LUT Date, e.g. 30/03/2026")
    ad_code: Optional[str] = Field(None, description="AD Code details")
    buyer_tax_id: Optional[str] = Field(None, description="Buyer NIF / tax id")

    # Shipment
    incoterms: Optional[str] = Field(None, description="Trade terms, e.g. 'CIF Singapore'")
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    vessel_flight: Optional[str] = None
    country_of_origin: Optional[str] = None
    pre_carriage: Optional[str] = Field(None, description="Pre-carriage by")
    place_of_receipt: Optional[str] = Field(None, description="Place of receipt by pre-carrier")
    country_of_destination: Optional[str] = Field(None, description="Country of final destination")
    final_destination: Optional[str] = Field(None, description="Final destination")
    terms_of_payment: Optional[str] = Field(None, description="Terms of payment text")
    terms_of_delivery: Optional[str] = Field(None, description="Terms of delivery details")

    # Packing details
    marks_and_nos: Optional[str] = Field(None, description="Marks & Nos aggregate details")
    pcs_count: Optional[str] = Field(None, description="Number of PCS")
    cartons_count: Optional[str] = Field(None, description="Number of Cartons")
    carton_dimension: Optional[str] = Field(None, description="Carton dimension details")
    total_net_weight: Optional[str] = Field(None, description="Total net weight")
    total_gross_weight: Optional[str] = Field(None, description="Total gross weight")

    # Declarations
    origin_declaration: Optional[str] = Field(None, description="Exporter origin declaration")
    invoice_declaration: Optional[str] = Field(None, description="Standard invoice accuracy declaration")

    # Financials
    currency: Optional[str] = Field(None, description="ISO currency code, e.g. 'USD'")
    item_table: List[CommercialInvoiceItem] = Field(default_factory=list)
    total_qty: Optional[str] = None
    total_value: Optional[str] = None
    amount_in_words: Optional[str] = None
    freight_charges: Optional[str] = None
    insurance_charges: Optional[str] = None

    # Other
    bank_details: BankDetails = Field(default_factory=BankDetails)
    signatory: Optional[str] = Field(None, description="Authorized signatory name/designation")
    declaration: Optional[str] = Field(None, description="Declaration / certification text at bottom")

    # Layout metadata (populated by vision LLM)
    layout: LayoutMeta = Field(default_factory=LayoutMeta)

    @model_validator(mode="before")
    @classmethod
    def _coerce_optional_strings(cls, values: Any) -> Any:
        """Coerce any Optional[str] field that arrives as int/float/bool to str."""
        if not isinstance(values, dict):
            return values
        str_fields = {
            "exporter","importer","notify_party","invoice_no","invoice_date",
            "iec_no","gst_no","po_no","lc_no","incoterms","port_of_loading",
            "port_of_discharge","vessel_flight","country_of_origin","currency",
            "total_qty","total_value","amount_in_words","freight_charges",
            "insurance_charges","signatory","declaration",
            "lut_arn","lut_date","ad_code","buyer_tax_id","pre_carriage","place_of_receipt",
            "country_of_destination","final_destination","terms_of_payment",
            "terms_of_delivery","marks_and_nos","pcs_count","cartons_count",
            "carton_dimension","total_net_weight","total_gross_weight",
            "origin_declaration","invoice_declaration"
        }
        out = dict(values)
        for f in str_fields:
            if f in out and out[f] is not None and not isinstance(out[f], str):
                out[f] = str(out[f])
        return out


# ---------------------------------------------------------------------------
# Packing List
# ---------------------------------------------------------------------------

class PackingListItem(BaseModel):
    model_config = {"extra": "ignore"}

    sr_no: Optional[str] = None
    description: str = Field(default="")
    hs_code: Optional[str] = None
    no_of_packages: Optional[str] = None
    package_type: Optional[str] = Field(None, description="e.g. 'Carton', 'Pallet'")
    gross_weight: Optional[str] = None
    net_weight: Optional[str] = None
    dimensions: Optional[str] = Field(None, description="L x W x H in cm or inches")

    @model_validator(mode="before")
    @classmethod
    def _coerce_all_to_str(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        return {k: str(v) if v is not None and not isinstance(v, str) else v
                for k, v in values.items()}


class PackingList(BaseModel):
    """Schema for a packing list document."""
    model_config = {"extra": "ignore"}

    doc_type: str = Field("packing_list", description="Fixed identifier for template selection")

    # Parties
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None

    # References
    invoice_ref: Optional[str] = Field(None, description="Related invoice number")
    bl_no: Optional[str] = Field(None, description="Bill of Lading number")
    packing_list_no: Optional[str] = None
    date: Optional[str] = None

    # Shipment
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    vessel_flight: Optional[str] = None
    country_of_origin: Optional[str] = None

    # Totals
    package_count: Optional[str] = Field(None, description="Total number of packages, e.g. '24 Cartons'")
    gross_weight: Optional[str] = Field(None, description="Total gross weight, e.g. '480.00 KGS'")
    net_weight: Optional[str] = Field(None, description="Total net weight, e.g. '440.00 KGS'")
    dimensions: Optional[str] = Field(None, description="Overall shipment dimensions")
    cbm: Optional[str] = Field(None, description="Cubic metres / volume")
    marks_and_numbers: Optional[str] = Field(None, description="Shipping marks / container markings (multiline)")

    # Items
    item_breakdown: List[PackingListItem] = Field(default_factory=list)

    # Signatures
    signatory: Optional[str] = None
    declaration: Optional[str] = None

    # Layout metadata
    layout: LayoutMeta = Field(default_factory=LayoutMeta)

    @model_validator(mode="before")
    @classmethod
    def _coerce_optional_strings(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        str_fields = {
            "shipper","consignee","notify_party","invoice_ref","bl_no",
            "packing_list_no","date","port_of_loading","port_of_discharge",
            "vessel_flight","country_of_origin","package_count","gross_weight",
            "net_weight","dimensions","cbm","marks_and_numbers","signatory","declaration",
        }
        out = dict(values)
        for f in str_fields:
            if f in out and out[f] is not None and not isinstance(out[f], str):
                out[f] = str(out[f])
        return out


# ---------------------------------------------------------------------------
# Generic Invoice
# ---------------------------------------------------------------------------

class InvoiceItem(BaseModel):
    model_config = {"extra": "ignore"}

    sr_no: Optional[str] = None
    description: str = Field(default="")
    qty: str = Field(default="")
    unit_price: str = Field(default="")
    amount: str = Field(default="")
    tax_rate: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_all_to_str(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        return {k: str(v) if v is not None and not isinstance(v, str) else v
                for k, v in values.items()}


class Invoice(BaseModel):
    """Schema for a generic (non-trade) invoice."""
    model_config = {"extra": "ignore"}

    doc_type: str = Field("invoice", description="Fixed identifier for template selection")

    # Parties
    seller: Optional[str] = Field(None, description="Seller / issuer name and address")
    buyer: Optional[str] = Field(None, description="Buyer / bill-to name and address")
    ship_to: Optional[str] = None

    # Reference
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_no: Optional[str] = None

    # Line items
    item_table: List[InvoiceItem] = Field(default_factory=list)

    # Totals
    subtotal: Optional[str] = None
    discount: Optional[str] = None
    tax_label: Optional[str] = Field(None, description="Tax label shown on document, e.g. 'GST 18%'")
    tax: Optional[str] = None
    shipping: Optional[str] = None
    total: Optional[str] = None
    amount_in_words: Optional[str] = None

    # Payment
    payment_terms: Optional[str] = None
    payment_method: Optional[str] = None
    bank_details: BankDetails = Field(default_factory=BankDetails)

    # Other
    notes: Optional[str] = None
    signatory: Optional[str] = None

    # Layout metadata
    layout: LayoutMeta = Field(default_factory=LayoutMeta)

    @model_validator(mode="before")
    @classmethod
    def _coerce_optional_strings(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        str_fields = {
            "seller","buyer","ship_to","invoice_no","invoice_date","due_date",
            "po_no","subtotal","discount","tax_label","tax","shipping","total",
            "amount_in_words","payment_terms","payment_method","notes","signatory",
        }
        out = dict(values)
        for f in str_fields:
            if f in out and out[f] is not None and not isinstance(out[f], str):
                out[f] = str(out[f])
        return out


# ---------------------------------------------------------------------------
# Union type used throughout the pipeline
# ---------------------------------------------------------------------------

DocumentData = CommercialInvoice | PackingList | Invoice


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

class IterationResult(BaseModel):
    """Per-iteration SSIM score and critic mismatch count."""
    iteration: int
    ssim_score: float
    mismatch_count: int


class ExtractionResponse(BaseModel):
    """Final response returned by POST /extract."""
    job_id: str
    doc_type: str
    template_ejs: str = Field(..., description="Full EJS template string")
    data_json: dict = Field(..., description="Extracted field values as a dict")
    final_ssim: float
    iterations: List[IterationResult]
    message: str = "OK"


class MismatchItem(BaseModel):
    """A single mismatch reported by the critic LLM."""
    category: str = Field(
        ...,
        description="One of: missing_field, wrong_value, wrong_position, wrong_alignment, "
                    "wrong_table_column, missing_table_row, wrong_font_style, wrong_color, other"
    )
    field_name: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    suggested_fix: Optional[str] = None


class CriticResponse(BaseModel):
    """Structured output from the critic LLM."""
    mismatches: List[MismatchItem] = Field(default_factory=list)
    overall_assessment: Optional[str] = None
