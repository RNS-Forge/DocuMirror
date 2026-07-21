import express, { Request, Response } from "express";
import path from "path";
import multer from "multer";
import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config({ path: path.join(__dirname, "..", ".env") });

// ---------------------------------------------------------------------------
// Gemini key pool — tries each key in order, rotates on quota / rate-limit
// ---------------------------------------------------------------------------
const GEMINI_KEY_POOL: string[] = [
  process.env.GEMINI_API_KEY_1,
  process.env.GEMINI_API_KEY_2,
  process.env.GEMINI_API_KEY_3,
  process.env.GEMINI_API_KEY_4,
].filter((k): k is string => !!k && k.trim().length > 0);

if (GEMINI_KEY_POOL.length === 0) {
  console.warn("Warning: GEMINI_API_KEY environment variable is not set. Live AI capabilities will be disabled.");
} else {
  console.log(`Gemini key pool: ${GEMINI_KEY_POOL.length} key(s) loaded.`);
}

let currentKeyIndex = 0;

function makeClient(keyIndex: number): GoogleGenAI {
  return new GoogleGenAI({
    apiKey: GEMINI_KEY_POOL[keyIndex] || "MOCK_KEY",
    httpOptions: { headers: { "User-Agent": "aistudio-build" } },
  });
}

async function generateWithFallback(
  params: Parameters<GoogleGenAI["models"]["generateContent"]>[0]
): Promise<ReturnType<GoogleGenAI["models"]["generateContent"]>> {
  const total = GEMINI_KEY_POOL.length;
  if (total === 0) throw new Error("No Gemini API keys configured.");

  let lastError: Error | null = null;

  for (let attempt = 0; attempt < total; attempt++) {
    const idx = (currentKeyIndex + attempt) % total;
    const client = makeClient(idx);
    try {
      const result = await client.models.generateContent(params);
      currentKeyIndex = idx;
      return result;
    } catch (err: any) {
      const msg: string = (err?.message || "").toLowerCase();
      const isQuota =
        err?.status === 429 ||
        msg.includes("quota") ||
        msg.includes("rate") ||
        msg.includes("limit") ||
        msg.includes("exhausted");
      if (isQuota) {
        console.warn(`[keys] Key #${idx + 1} hit quota/rate-limit — rotating to next key.`);
        lastError = err;
        continue;
      }
      throw err;
    }
  }

  throw lastError || new Error("All Gemini API keys have been exhausted.");
}

const app = express();
const PORT = parseInt(process.env.NODE_PORT || "3000", 10);

// Increase payload limit for base64 image uploads
app.use(express.json({ limit: "50mb" }));
app.use(express.urlencoded({ limit: "50mb", extended: true }));

const STATIC_DIR = path.join(__dirname, "..", "static");
app.use(express.static(STATIC_DIR));

// Multer — memory storage, 50 MB limit
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 50 * 1024 * 1024 },
});

// ---------------------------------------------------------------------------
// Explicit page routes
// ---------------------------------------------------------------------------
app.get("/", (_req: Request, res: Response) => {
  res.sendFile(path.join(STATIC_DIR, "index.html"));
});

app.get("/upload", (_req: Request, res: Response) => {
  res.sendFile(path.join(STATIC_DIR, "upload.html"));
});

app.get("/editor", (_req: Request, res: Response) => {
  res.sendFile(path.join(STATIC_DIR, "codeeditor.html"));
});

// ---------------------------------------------------------------------------
// Preloaded high-fidelity sample templates (verbatim from reference)
// ---------------------------------------------------------------------------
const sampleTemplates: Record<string, { html: string; name: string; description: string }> = {
  sample1: {
    name: "Commercial Invoice (Landscape - Polo Shirts)",
    description: "The custom landscape grid style matching Dibella India exporter & Brands Fashion GmbH buyer.",
    html: `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Commercial Invoice - Dibella India</title>
    <style>
        @page { size: A4 landscape; margin: 8mm; }
        body { font-family: 'Inter', Arial, sans-serif; font-size: 10px; margin: 0; color: #000; background-color: #fff; }
        table { width: 100%; border-collapse: collapse; table-layout: fixed; }
        td, th { border: 1px solid #000; padding: 4px 5px; vertical-align: top; word-wrap: break-word; }
        .title { text-align: center; font-size: 13px; font-weight: bold; padding: 6px 0; background-color: #f3f4f6; letter-spacing: 1px; }
        .bold { font-weight: bold; }
        .center { text-align: center; }
        .right { text-align: right; }
        .no-border { border-style: hidden !important; }
        .no-border-bottom { border-bottom-style: hidden !important; }
        .no-border-top { border-top-style: hidden !important; }
        .no-border-right { border-right-style: hidden !important; }
        .no-border-left { border-left-style: hidden !important; }
        .header-label { font-size: 8px; text-transform: uppercase; color: #4b5563; display: block; margin-bottom: 2px; font-weight: 600; }
        .section-desc { font-size: 9px; color: #1f2937; line-height: 1.3; }
        th { background-color: #f9fafb; font-weight: bold; text-align: center; font-size: 9px; }
        .bg-gray { background-color: #f9fafb; }
    </style>
</head>
<body>
    <table>
        <tr><td colspan="12" class="title">COMMERCIAL INVOICE</td></tr>
        <tr>
            <td colspan="6" rowspan="2">
                <span class="header-label">Exporter / Shipper:-</span>
                <span class="bold">Dibella India</span><br>
                B-309, Anisha Grange,<br>29th Cross, Kaggadasapura,<br>Bangalore, Karnataka - 560093, India
            </td>
            <td colspan="3" class="no-border-right no-border-bottom"><span class="header-label">Invoice No.</span><span class="bold">DI-EXP/26-27/051</span></td>
            <td colspan="3" class="no-border-left no-border-bottom"><span class="header-label">Date</span><span class="bold">07-May-26</span></td>
        </tr>
        <tr>
            <td colspan="3" class="no-border-right no-border-top"><span class="header-label">Buyers Order No.</span><span>A-948123 / PO-901</span></td>
            <td colspan="3" class="no-border-left no-border-top"><span class="header-label">AEO No.</span><span>ARRPS6899K2F262</span></td>
        </tr>
        <tr>
            <td colspan="3"><span class="header-label">Consignee / Buyer</span><span class="bold">Brands Fashion GmbH</span><br>Muellerstraße 11<br>21244 Buchholz<br>Germany<br>DE813536507<br>EORI: DE4789849</td>
            <td colspan="3"><span class="header-label">Delivery Address</span><span class="bold">BRANDS Fashion GmbH</span><br>Am Ring 11<br>19376 Ruhner Berge OT Zachow<br>Germany</td>
            <td colspan="6"><span class="header-label">Exporter Bank Details:-</span>Account Name: <span class="bold">Dibella India</span><br>Bank Name: <span class="bold">Kotak Mahindra Bank Ltd</span><br>Branch: 22, Ground Floor, MG Road, Bangalore - 560001, Karnataka, India.<br>Account No: <span class="bold">0749510877</span><br>SWIFT Code: <span class="bold">KKBKINBBCPC</span></td>
        </tr>
        <tr>
            <td colspan="3"><span class="header-label">Pre-Carriage By</span>By Road</td>
            <td colspan="3"><span class="header-label">Place of Receipt by Pre Carrier</span>Bangalore</td>
            <td colspan="3"><span class="header-label">Country of Origin</span>India</td>
            <td colspan="3"><span class="header-label">Country of Final Destination</span>Germany</td>
        </tr>
        <tr>
            <td colspan="3"><span class="header-label">Vessel / Flight No.</span>By Sea</td>
            <td colspan="3"><span class="header-label">Port of Loading</span>CHENNAI</td>
            <td colspan="3"><span class="header-label">Payment Terms</span>T/T against delivery</td>
            <td colspan="3"><span class="header-label">Incoterms</span><span class="bold">FOB SEA-CHENNAI-INDIA</span></td>
        </tr>
        <tr>
            <td colspan="3"><span class="header-label">Port of Discharge</span>Hamburg, Germany</td>
            <td colspan="3"><span class="header-label">Final Destination</span>Hamburg, Germany</td>
            <td colspan="6"><span class="header-label">Exporter References</span>IEC NO: 0713012480,   GST: 29ARRPS6899K1Z9 <br>LUT NO(ARN): AD290326068585K   DT: 30/03/2026   AD Code: 0180980</td>
        </tr>
        <tr>
            <th style="width:10%">Shipping Marks</th>
            <th colspan="5" style="width:45%">Description of the Goods</th>
            <th style="width:10%">Size</th>
            <th style="width:8%">Color</th>
            <th style="width:9%">HSN Code</th>
            <th style="width:8%">Qty (PCS)</th>
            <th style="width:10%">Unit Price (GBP)</th>
            <th style="width:10%">Amount (GBP)</th>
        </tr>
        <tr class="center">
            <td class="no-border-bottom">DI-01</td>
            <td colspan="5" class="no-border-bottom" style="text-align:left">50% COTTON 50% POLYESTER KNITTED BOYS POLO T-SHIRT</td>
            <td class="no-border-bottom">3-4 - 11-12</td>
            <td class="no-border-bottom bold">PLAIN</td>
            <td class="no-border-bottom">61051090</td>
            <td class="no-border-bottom">1,243</td>
            <td class="no-border-bottom right">£ 5.12</td>
            <td class="right no-border-bottom">£ 6,364.16</td>
        </tr>
        <tr class="center">
            <td class="no-border-bottom no-border-top">DI-02</td>
            <td colspan="5" class="no-border-bottom no-border-top" style="text-align:left">50% COTTON 50% POLYESTER KNITTED GIRLS POLO T-SHIRT</td>
            <td class="no-border-bottom no-border-top">3-4 - 11-12</td>
            <td class="no-border-bottom no-border-top bold">PLAIN</td>
            <td class="no-border-bottom no-border-top">61051090</td>
            <td class="no-border-bottom no-border-top">980</td>
            <td class="no-border-bottom no-border-top right">£ 5.12</td>
            <td class="right no-border-bottom no-border-top">£ 5,017.60</td>
        </tr>
        <tr class="center">
            <td class="no-border-bottom no-border-top">DI-03</td>
            <td colspan="5" class="no-border-bottom no-border-top" style="text-align:left">100% COTTON KNITTED UNISEX T-SHIRT WITH EMBROIDERY</td>
            <td class="no-border-bottom no-border-top">S - XXL</td>
            <td class="no-border-bottom no-border-top bold">NAVY</td>
            <td class="no-border-bottom no-border-top">61091000</td>
            <td class="no-border-bottom no-border-top">952</td>
            <td class="no-border-bottom no-border-top right">£ 4.48</td>
            <td class="right no-border-bottom no-border-top">£ 4,264.96</td>
        </tr>
        <tr>
            <td class="no-border-bottom no-border-top" style="height:20px"></td>
            <td colspan="5" class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
        </tr>
        <tr>
            <td class="no-border-bottom no-border-top"></td>
            <td colspan="7" class="no-border-bottom no-border-top section-desc">
                The exporter of the products covered by this document (customs identification number "0713012480") declares that,
                except where otherwise clearly indicated, these products are of INDIA origin preferential origin in accordance with
                the rules of origin of the Developing Countries Trading Scheme of UK and that the origin criterion met is 'P'.
            </td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
        </tr>
        <tr>
            <td class="no-border-bottom no-border-top" style="height:20px"></td>
            <td colspan="5" class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
        </tr>
        <tr>
            <td class="no-border-bottom no-border-top"></td>
            <td colspan="5" class="no-border-bottom no-border-top">
                <span class="bold">PACKING DETAILS:-</span><br>
                Total Number of Cartons: 112 CTNS<br>Carton Dimension: 58X38X35 CM<br>
                Total Net Weight: 1,842.50 KGS<br>Total Gross Weight: 2,120.00 KGS<br>CBM: 16.80 CBM
            </td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
            <td class="no-border-bottom no-border-top"></td><td class="no-border-bottom no-border-top"></td>
        </tr>
        <tr class="bold bg-gray">
            <td>Total: 112 CTNS</td><td colspan="5"></td><td></td><td></td>
            <td class="right">Total:-</td><td class="center">3,175</td>
            <td class="right">Total:-</td><td class="right">£ 15,646.72</td>
        </tr>
        <tr>
            <td colspan="6" class="no-border-right"><span class="header-label">Amount in words (GBP)</span><span class="bold">Fifteen Thousand Six Hundred Forty Six Pounds and Seventy Two Pence Only.</span></td>
            <td class="no-border-left no-border-right center"><span class="header-label">Ex. Rate</span><span>90.42</span></td>
            <td class="no-border-left center" colspan="1"><span class="header-label">FOB INR Value</span><span>1,414,776.42</span></td>
            <td colspan="4" class="no-border-bottom"><span class="header-label">For Exporter</span><span class="bold">For Dibella India</span></td>
        </tr>
        <tr>
            <td colspan="8"><span class="bold">Statement of Origin:</span> The exporter INREX0713012480TC003 of the products covered by this document declares that, except where otherwise clearly indicated, these products are of INDIAN Preferential Origin according to rules of origin of Generalised System of Preferences of European Union - and that the origin criterion met is "W".<br><br><span class="bold">Declaration:</span> We declare that this Invoice shows the actual price of the goods described and that all particulars are true and correct.</td>
            <td colspan="4" class="no-border-top" style="vertical-align:bottom;height:60px;text-align:center"><span class="header-label" style="text-align:center">Authorized Signatory</span><br><div style="border-top:1px dashed #6b7280;width:80%;margin:0 auto;padding-top:4px">Authorized Representative</div></td>
        </tr>
    </table>
</body>
</html>`,
  },
  sample2: {
    name: "Commercial Invoice (Portrait - Clipper Target Woven Bags)",
    description: "Multi-item vertical/portrait layout featuring 100% organic fairtrade cotton woven bags.",
    html: `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Commercial Invoice - Clipper Target Sourcing</title>
    <style>
        @page { size: A4 portrait; margin: 10mm; }
        body { font-family: 'Inter', Arial, sans-serif; font-size: 9px; margin: 0; color: #000; background-color: #fff; }
        .container { width: 100%; border: 1px solid #000; }
        .main-title { text-align: center; font-size: 14px; font-weight: bold; padding: 8px 0; border-bottom: 2px solid #000; letter-spacing: 1.5px; text-transform: uppercase; }
        .grid-half { display: grid; grid-template-columns: 1fr 1fr; border-bottom: 1px solid #000; }
        .grid-cell { padding: 6px; border-right: 1px solid #000; }
        .grid-cell:last-child { border-right: none; }
        .cell-label { font-size: 8px; text-transform: uppercase; font-weight: bold; color: #374151; display: block; margin-bottom: 3px; }
        .cell-value { font-size: 10px; line-height: 1.3; }
        .cell-value.bold { font-weight: bold; }
        .grid-four { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; border-bottom: 1px solid #000; }
        table.items-table { width: 100%; border-collapse: collapse; border-bottom: 1px solid #000; }
        table.items-table th { border-right: 1px solid #000; border-bottom: 2px solid #000; padding: 6px; font-size: 8px; text-transform: uppercase; font-weight: bold; background-color: #f9fafb; }
        table.items-table th:last-child { border-right: none; }
        table.items-table td { border-right: 1px solid #000; border-bottom: 1px solid #000; padding: 5px 6px; font-size: 9px; vertical-align: top; }
        table.items-table td:last-child { border-right: none; }
        table.items-table tr:last-child td { border-bottom: none; }
        .right { text-align: right; } .center { text-align: center; } .bold { font-weight: bold; }
        .footer-words { padding: 8px; border-bottom: 1px solid #000; font-size: 9px; }
        .footer-bank { padding: 8px; border-bottom: 1px solid #000; display: grid; grid-template-columns: 2fr 1fr; }
        .declaration-box { padding: 8px; font-size: 8px; line-height: 1.4; color: #4b5563; }
    </style>
</head>
<body>
    <div class="container">
        <div class="main-title">COMMERCIAL INVOICE</div>
        <div class="grid-half">
            <div class="grid-cell"><span class="cell-label">Exporter / Seller</span><div class="cell-value bold">DIBELLA INDIA</div><div class="cell-value">B-309, Anisha Grange, 29th Cross, Kaggadasapura,<br>Bangalore, Karnataka - 560093, India</div></div>
            <div class="grid-cell"><span class="cell-label">Importer / Consignee</span><div class="cell-value bold">Clipper Target Sourcing Lda</div><div class="cell-value">Rua Palmira Silva Lote 30i, 8600-785 Lagos, Portugal</div></div>
        </div>
        <div class="grid-half" style="grid-template-columns:1fr">
            <div class="grid-cell" style="border-right:none"><span class="cell-label">Notify Party / Delivery Address</span><div class="cell-value bold">Textillogistik Unna - Tor F</div><div class="cell-value">Anlieferung, Otto-Hahn-Str. 27, 59423 Unna, Germany</div></div>
        </div>
        <div class="grid-half">
            <div class="grid-cell"><span class="cell-label">Invoice No.</span><div class="cell-value bold">DI-EXP/26-27/088</div></div>
            <div class="grid-cell"><span class="cell-label">Invoice Date</span><div class="cell-value bold">10-Jun-26</div></div>
        </div>
        <div class="grid-half">
            <div class="grid-cell"><span class="cell-label">IEC No / ID Code</span><div class="cell-value">0713012480</div></div>
            <div class="grid-cell"><span class="cell-label">GST / VAT NO.</span><div class="cell-value">29ARRPS6899K1Z9</div></div>
        </div>
        <div class="grid-four">
            <div class="grid-cell"><span class="cell-label">P.O. No.</span><div class="cell-value">010-BA00107800</div></div>
            <div class="grid-cell"><span class="cell-label">Incoterms</span><div class="cell-value bold">CIF Rotterdam - BY SEA</div></div>
            <div class="grid-cell"><span class="cell-label">Currency</span><div class="cell-value">EURO</div></div>
            <div class="grid-cell"><span class="cell-label">Port of Loading</span><div class="cell-value">Tuticorin</div></div>
        </div>
        <div class="grid-four" style="grid-template-columns:1fr 1fr">
            <div class="grid-cell"><span class="cell-label">Port of Discharge</span><div class="cell-value bold">ROTTERDAM</div></div>
            <div class="grid-cell"><span class="cell-label">Vessel / Flight No.</span><div class="cell-value">BY SEA</div></div>
        </div>
        <div class="grid-half" style="grid-template-columns:1fr">
            <div class="grid-cell" style="border-right:none"><span class="cell-label">Country of Origin</span><div class="cell-value bold">INDIA</div></div>
        </div>
        <table class="items-table">
            <thead>
                <tr>
                    <th style="width:5%">SR</th>
                    <th style="width:55%;text-align:left">Description of Goods</th>
                    <th style="width:12%">HS Code</th>
                    <th style="width:10%;text-align:center">Quantity (PCS)</th>
                    <th style="width:8%;text-align:right">Unit Price</th>
                    <th style="width:10%;text-align:right">Amount</th>
                </tr>
            </thead>
            <tbody>
                <tr><td class="center">1</td><td>100% organic fairtrade cotton woven bags (Size 38 x 42 with long handles - handle size 2.5cm x 70cm)</td><td class="center">42022220</td><td class="center">126,750</td><td class="right">€ 0.63</td><td class="right">€ 79,852.50</td></tr>
                <tr><td class="center">2</td><td>100% organic fairtrade cotton woven bags (Size 38 x 42 with long handles - handle size 2.5cm x 70cm)</td><td class="center">42022220</td><td class="center">31,000</td><td class="right">€ 0.87</td><td class="right">€ 26,970.00</td></tr>
                <tr><td class="center">3</td><td>100% organic fairtrade cotton woven bags (Size 38 x 42 with long handles - handle size 2.5cm x 70cm)</td><td class="center">42022220</td><td class="center">12,250</td><td class="right">€ 0.87</td><td class="right">€ 10,657.50</td></tr>
                <tr><td class="center">4</td><td>100% organic cotton woven vegetable mesh bags</td><td class="center">42022220</td><td class="center">10,250</td><td class="right">€ 0.87</td><td class="right">€ 8,917.50</td></tr>
                <tr><td class="center">5</td><td>100% organic fairtrade cotton woven oversize bag with gusset on three sides</td><td class="center">42022220</td><td class="center">3,250</td><td class="right">€ 0.85</td><td class="right">€ 2,762.50</td></tr>
                <tr class="bold bg-gray" style="border-top:2px solid #000"><td></td><td class="right">Total</td><td></td><td class="center">183,500</td><td></td><td class="right">€ 129,160.00</td></tr>
            </tbody>
        </table>
        <div class="footer-words"><span class="cell-label">Amount in Words (EURO)</span><div class="bold" style="text-transform:uppercase">One Hundred Twenty-Nine Thousand One Hundred Sixty Euros Only.</div></div>
        <div class="footer-bank">
            <div><span class="cell-label">Bank Details</span><div class="cell-value">Bank: <span class="bold">DIBELLA INDIA / Kotak Mahindra Bank</span><br>A/C No.: <span class="bold">0749510877</span><br>SWIFT: <span class="bold">KKBKINBBCPC</span><br>Branch: 22, Ground Floor, MG Road, Bangalore-Karnataka- India.</div></div>
            <div style="border-left:1px solid #000;padding-left:10px;display:flex;flex-direction:column;justify-content:space-between"><span class="cell-label" style="text-align:center">Authorised Signatory</span><div style="border-top:1px dashed #000;text-align:center;font-size:8px;padding-top:4px">Authorized Representative</div></div>
        </div>
        <div class="declaration-box">We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.</div>
    </div>
</body>
</html>`,
  },
  sample3: {
    name: "Commercial Invoice (Landscape - Knit Beanies)",
    description: "Detailed landscape layout representing Westcoast of Sweden Intl AB buyer for knit caps.",
    html: `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Commercial Invoice - Westcoast of Sweden</title>
    <style>
        @page { size: A4 landscape; margin: 8mm; }
        body { font-family: 'Inter', Arial, sans-serif; font-size: 9px; margin: 0; color: #000; background-color: #fff; }
        table { width: 100%; border-collapse: collapse; table-layout: fixed; }
        td, th { border: 1px solid #000; padding: 4px 5px; vertical-align: top; word-wrap: break-word; }
        .title { text-align: center; font-size: 13px; font-weight: bold; padding: 5px 0; background-color: #f3f4f6; letter-spacing: 1.5px; }
        .bold { font-weight: bold; } .center { text-align: center; } .right { text-align: right; }
        .header-label { font-size: 7.5px; text-transform: uppercase; color: #4b5563; display: block; margin-bottom: 2px; font-weight: 600; }
        .cell-value { font-size: 9.5px; line-height: 1.25; }
    </style>
</head>
<body>
    <table>
        <tr><td colspan="12" class="title">COMMERCIAL INVOICE</td></tr>
        <tr>
            <td colspan="4" rowspan="2"><span class="header-label">Exporter / Shipper:-</span><span class="bold">Dibella India</span><br>B-309, Anisha Grange, 29th Cross, Kaggadasapura,<br>Bangalore, Karnataka - 560093, India<br>IEC NO: 0713012480, AD Code: 0180980, GST:29ARRPS6899K1Z9</td>
            <td colspan="4"><span class="header-label">Invoice No.</span><span class="bold">DI-EXP/26-27/042</span></td>
            <td colspan="4"><span class="header-label">Exporter Bank Details:-</span>Account Name: <span class="bold">Dibella India</span><br>Bank Name: <span class="bold">Kotak Mahindra Bank Ltd</span><br>Branch: MG Road, Bangalore. Account No: <span class="bold">0749510877</span><br>SWIFT: <span class="bold">KKBKINBBCPC</span></td>
        </tr>
        <tr>
            <td colspan="4"><span class="header-label">Invoice Date</span><span class="bold">2-May-26</span></td>
            <td colspan="4"><span class="header-label">LUT NO. (ARN)</span><span>AD290326068585K DT 30/03/2026</span></td>
        </tr>
        <tr>
            <td colspan="6"><span class="header-label">Buyer Address:-</span><span class="bold">Westcoast of Sweden Intl AB</span><br>Backegardsvagen 1, 459 30 Ljungskile, Sweden<br>Phone: +46 522-587284. email: info@blackhill.se</td>
            <td colspan="6"><span class="header-label">Consignee Address:-</span><span class="bold">Westcoast of Sweden Intl AB</span><br>Backegardsvagen 1, 459 30 Ljungskile, Sweden<br>Phone: +46 522-587284. email: info@blackhill.se</td>
        </tr>
        <tr>
            <td colspan="3"><span class="header-label">Pre-Carriage By</span>By Road</td>
            <td colspan="3"><span class="header-label">Place of Receipt by Pre Carrier</span>Bangalore</td>
            <td colspan="3"><span class="header-label">Country of Origin</span>India</td>
            <td colspan="3"><span class="header-label">Country of Final Destination</span>Sweden</td>
        </tr>
        <tr>
            <td colspan="3"><span class="header-label">Vessel / Flight No.</span>By Sea</td>
            <td colspan="3"><span class="header-label">Port of Loading</span>TUTICORIN</td>
            <td colspan="3"><span class="header-label">Payment Terms</span>Against Documents</td>
            <td colspan="3"><span class="header-label">Incoterms</span><span class="bold">FOB-SEA / TUTICORIN-INDIA</span></td>
        </tr>
        <tr>
            <th>Shipping Marks &amp; Number</th><th>Purchase Order Number</th><th>Style Number</th>
            <th colspan="3">Description of Goods</th><th>Style Name</th><th>HSN Code</th>
            <th>Quantity in PCS</th><th>Unit Price in EURO</th><th colspan="2">Amount in EURO</th>
        </tr>
        <tr class="center">
            <td style="text-align:left">WSI<br>Order no:<br>S-294842 Akademiker<br>Colour: Black<br>GW:<br>Meas:<br>Qty/ctn:<br>Ctn.no:</td>
            <td>S-294842<br>Akademiker</td><td>140964</td>
            <td colspan="3" style="text-align:left">95% COTTON 5% ELASTNAE KNITTED BEANIE CAP</td>
            <td>BEANIE CAP<br>( Beanie Tyra )</td><td>65050090</td><td>3000</td>
            <td class="right">€ 2.00</td><td colspan="2" class="right">€ 6,000.00</td>
        </tr>
        <tr>
            <td style="height:100px"></td><td></td><td></td><td colspan="3"></td>
            <td></td><td></td><td></td><td></td><td colspan="2"></td>
        </tr>
        <tr class="bold" style="background-color:#f9fafb">
            <td colspan="8" class="right">Total:-</td><td class="center">3000</td>
            <td class="right">Total:-</td><td colspan="2" class="right">€ 6,000.00</td>
        </tr>
        <tr>
            <td colspan="8" style="vertical-align:top"><span class="header-label">Amount in Words EURO:</span><span class="bold">SIX THOUSAND ONLY</span></td>
            <td style="vertical-align:top"><span class="header-label" style="font-size:7px;color:#555">EX-RATE</span><span class="bold" style="display:block;margin-top:4px;font-size:10px">108.45</span></td>
            <td style="vertical-align:top"><span class="header-label" style="font-size:7px;color:#555">FOB INR</span><span class="bold" style="display:block;margin-top:4px;font-size:10px">650,700.00</span></td>
            <td colspan="2" rowspan="3" style="vertical-align:top;border-left:1px solid #000"><span class="header-label">For Dibella India</span><div style="height:75px"></div><div class="center" style="border-top:1px dashed #6b7280;font-size:8px;width:90%;margin:0 auto;padding-top:4px;font-weight:bold">Authorised Signatory</div></td>
        </tr>
        <tr>
            <td colspan="8" style="vertical-align:top"><span class="bold" style="font-size:8px;text-transform:uppercase">Statement of Origin:</span><span style="font-size:8px;line-height:1.3"> The exporter INREX0713012480TC003 of the products covered by this document declares that, except where otherwise clearly indicated these products are of INDIAN Preferential Origin according to rules of origin of Generalised System of Preferences of European Union - and that the origin criterion met is "P"</span></td>
            <td colspan="2" rowspan="2" style="vertical-align:top;border-left:1px solid #000;font-size:8px;line-height:1.4"><span class="bold" style="text-transform:uppercase;font-size:7px;color:#4b5563;display:block;margin-bottom:3px">Packing Details:</span>Number of PKG: <span class="bold">30 Boxes</span><br>Carton Dimension: <span class="bold">48X48X20 In CM</span><br>Total Net Weight: <span class="bold">183.00 Kgs</span><br>Total Gross Weight: <span class="bold">226.50 Kgs</span></td>
        </tr>
        <tr>
            <td colspan="8" style="vertical-align:top;border-top:1px solid #000"><span class="bold" style="font-size:8px;text-transform:uppercase">Declaration:</span><span style="font-size:8px;line-height:1.3"> We declare that this Invoice shows the actual price of the goods described and that all particulars are true and correct.</span></td>
        </tr>
    </table>
</body>
</html>`,
  },
};


// ---------------------------------------------------------------------------
// Shared digitize prompt — verbatim from reference
// ---------------------------------------------------------------------------
const DIGITIZE_PROMPT = `You are an absolute master commercial invoice and packing list designer, and an ultra-high-accuracy OCR engine.
Analyze the provided document image (which can be a Commercial Invoice or a Packing List) and reconstruct it into an extremely precise, professional, and visually flawless single-file HTML/CSS document.

CRITICAL INSTRUCTIONS FOR MAXIMUM ACCURACY, PERFECT ALIGNMENTS, AND BORDER RENDERING:

1. EXPLICIT TABLE BORDERS & GRIDLINES:
   - Apply 'border-collapse: collapse;' to the main <table>.
   - Every single <td> and <th> must have crisp, explicit solid black/charcoal borders (e.g., 'border: 1px solid #000;' or 'border: 1px solid #222;').
   - BORDER-HIDING/OVERRIDING: When 'border-collapse: collapse;' is active, browser rendering engines select conflicting cell borders according to thickness rules. Thus, setting 'border-right: none;' will NOT hide a border if the adjacent cell defines a border. To guarantee that a specific cell border is hidden, you MUST use 'border-right-style: hidden !important;' (or top/bottom/left as appropriate). Always define helper classes in your style block:
     .no-border { border-style: hidden !important; }
     .no-border-bottom { border-bottom-style: hidden !important; }
     .no-border-top { border-top-style: hidden !important; }
     .no-border-right { border-right-style: hidden !important; }
     .no-border-left { border-left-style: hidden !important; }
   - Ensure the borders form a solid, continuous grid with NO double borders or broken, disjointed line segments.
   - Do NOT use nested tables if they create misaligned outer boundaries or double borders. Prefer a unified 12-column, 16-column, or 24-column layout with mathematically precise 'colspan' values across rows (the colspans of every single row must sum up to the exact same total column count).

2. HANDLING OF EX-RATE, FOB, PACKING LIST DETAILS, AND SIGNATORY BOXES:
   - This section must be rendered with perfect border alignments. In many documents, the EX-RATE, FOB INR/rate, signature box, and invoice data are at the bottom. Ensure that they are fully enclosed in table cells that align perfectly with the columns of the main table or are properly formatted in a row that shares the exact same grid boundaries.
   - If there is a 'Statement of Origin' or 'Declaration' row on the bottom left, and a signature box like 'For Dibella India / Authorised Signatory' on the bottom right, and a 'Packing Details' (Number of PKG, Carton Dimension, Net/Gross weight) in the middle/right, arrange them with precise rowspan/colspan so they are perfectly aligned horizontally and vertically.
   - The signature box must have a clean dashed/dotted line and be positioned in a dedicated right-hand cell with a clear border: 'border-left: 1px solid #000;'.
   - Ensure numeric figures such as EX-RATE (e.g. '108.45'), FOB rate/INR (e.g. '650,700.00'), Total cartons, and currency values are transcribed exactly, aligned properly with their descriptive labels, and styled cleanly.

3. DYNAMIC PACKING LIST GRID HANDLING:
   - If the uploaded image is a "PACKING LIST", reconstruct the layout perfectly, including any complex "Size Wise Breakup" or "Carton Breakup" headers.
   - Carefully count and layout the sub-headers (e.g., XS, S, M, L, XL, XXL, 3XL, 4XL, OS or 34/XXS, 36/XS, 38/S, 40/M, 42/L, 44/XL, 46/XXL) with explicit headers and perfectly matching vertical columns.
   - Maintain the alternating light green/light orange color highlights for total rows if present in the source image, or use clean, professional pastel tones to distinguish them.
   - Keep the itemized table rows complete. Extract every single row with exact details of Carton Serial Number, Carton Nos, PO Number, Color Code, Goods Description, quantity per carton, total quantity, dimensions, net weight, gross weight, and CBM.

4. 100% TRANSCRIPTION ACCURACY (NO SUMMARIZATION):
   - Transcribe every printed character, word, and number with 100% fidelity.
   - Extract ALL critical codes: IEC Number, GST/VAT ID, AEO Code, LUT Number, Bank Account Details (Branch address, Account number, SWIFT/IBAN code), HSN/HS codes, Style numbers, Buyers Order Numbers, and Port of Loading.
   - Do NOT replace text blocks with placeholders like '...' or '[rest of address]'. Transcribe all legal texts, declarations (e.g., UK GSP/Developing Countries Preference Schemes, Preferential Origin), and signature details exactly.

5. LAYOUT & TYPOGRAPHY STYLE:
   - Use standard clean modern sans-serif fonts (e.g., 'Inter', system-ui, Arial) for high readability.
   - Use small, clear, compact typography (typically font-size: 8px to 10px; line-height: 1.3) with subtle bold labels to mimic high-quality customs documents.
   - Match orientation exactly. If the document is landscape, define '@media print { @page { size: A4 landscape; margin: 8mm; } }'. If portrait, define A4 portrait with standard 10mm margins.
   - Return ONLY the absolute raw complete HTML string starting with <!DOCTYPE html> and ending with </html>.
   - Do NOT wrap the code in markdown code blocks (such as \`\`\`html) or include any conversational intro/outro text. Return ONLY the raw executable template.`;

// ---------------------------------------------------------------------------
// Helper: strip accidental markdown code fences from Gemini output
// ---------------------------------------------------------------------------
function cleanHtml(raw: string): string {
  let h = raw.trim();
  if (h.startsWith("```html")) h = h.substring(7);
  else if (h.startsWith("```")) h = h.substring(3);
  if (h.endsWith("```")) h = h.substring(0, h.length - 3);
  return h.trim();
}

// ---------------------------------------------------------------------------
// GET /api/samples
// ---------------------------------------------------------------------------
app.get("/api/samples", (_req: Request, res: Response) => {
  const metadata = Object.entries(sampleTemplates).map(([id, s]) => ({
    id,
    name: s.name,
    description: s.description,
  }));
  res.json(metadata);
});

// ---------------------------------------------------------------------------
// GET /api/sample/:id
// ---------------------------------------------------------------------------
app.get("/api/sample/:id", (req: Request, res: Response) => {
  const { id } = req.params;
  const sample = sampleTemplates[id];
  if (!sample) return res.status(404).json({ error: "Sample not found" });
  res.json({ html: sample.html });
});

// ---------------------------------------------------------------------------
// POST /api/upload — PDF or image file → Gemini → HTML
// ---------------------------------------------------------------------------
app.post("/api/upload", upload.single("file"), async (req: Request, res: Response) => {
  try {
    if (!req.file) return res.status(400).json({ error: "No file uploaded." });

    const { mimetype, buffer, originalname } = req.file;
    const isPdf = mimetype === "application/pdf" || (originalname || "").toLowerCase().endsWith(".pdf");

    if (GEMINI_KEY_POOL.length === 0) {
      return res.status(503).json({
        error: "Gemini API Key is not configured. Please add your key in the Secrets/Settings panel to digitize custom uploaded images.",
      });
    }

    // Gemini 2.5 Flash natively supports PDF inline — pass directly
    const base64Data = buffer.toString("base64");
    const dataMime = isPdf ? "application/pdf" : mimetype;

    console.log(`Sending ${isPdf ? "PDF" : "image"} (${(buffer.length / 1024).toFixed(0)} KB) to Gemini...`);

    const response = await generateWithFallback({
      model: "gemini-2.5-flash",
      contents: { parts: [{ inlineData: { mimeType: dataMime, data: base64Data } }, { text: DIGITIZE_PROMPT }] },
    });

    const generatedText = response.text || "";
    const cleanedHtml = cleanHtml(generatedText);
    if (!cleanedHtml) return res.status(500).json({ error: "Gemini returned an empty response." });

    res.json({ html: cleanedHtml });
  } catch (error: any) {
    console.error("Error digitizing invoice with Gemini:", error);
    res.status(500).json({
      error: error.message || "An error occurred while communicating with the Gemini API. Please make sure your API key is correct.",
    });
  }
});

// ---------------------------------------------------------------------------
// POST /api/digitize — base64 image in request body
// ---------------------------------------------------------------------------
app.post("/api/digitize", async (req: Request, res: Response) => {
  try {
    const { image, mimeType } = req.body;
    if (!image) return res.status(400).json({ error: "No image payload found in request" });

    let cleanBase64 = image;
    let cleanMimeType = mimeType || "image/jpeg";

    if (image.includes(";base64,")) {
      const parts = image.split(";base64,");
      const mimePart = parts[0];
      cleanBase64 = parts[1];
      const match = mimePart.match(/data:(image\/\w+)/);
      if (match) cleanMimeType = match[1];
    }

    if (GEMINI_KEY_POOL.length === 0) {
      return res.status(503).json({
        error: "Gemini API Key is not configured. Please add your key in the Secrets/Settings panel to digitize custom uploaded images.",
      });
    }

    const imagePart = { inlineData: { mimeType: cleanMimeType, data: cleanBase64 } };
    const textPart = { text: DIGITIZE_PROMPT };

    console.log("Sending commercial invoice image to Gemini...");
    const response = await generateWithFallback({
      model: "gemini-2.5-flash",
      contents: { parts: [imagePart, textPart] },
    });

    const generatedText = response.text || "";
    const cleanedHtml = cleanHtml(generatedText);
    res.json({ html: cleanedHtml });
  } catch (error: any) {
    console.error("Error digitizing invoice with Gemini:", error);
    res.status(500).json({
      error: error.message || "An error occurred while communicating with the Gemini API. Please make sure your API key is correct.",
    });
  }
});

// ---------------------------------------------------------------------------
// POST /api/refine — AI-powered visual/content refinement
// ---------------------------------------------------------------------------
app.post("/api/refine", async (req: Request, res: Response) => {
  try {
    const { html, prompt } = req.body;
    if (!html) return res.status(400).json({ error: "Missing HTML code to refine" });
    if (!prompt) return res.status(400).json({ error: "Missing refinement prompt instructions" });

    if (GEMINI_KEY_POOL.length === 0) {
      return res.status(503).json({
        error: "Gemini API Key is not configured. Please add your key in the Secrets/Settings panel to refine templates.",
      });
    }

    console.log("Sending refinement request to Gemini...");
    const response = await generateWithFallback({
      model: "gemini-2.5-flash",
      contents: `You are an expert HTML email and commercial invoice front-end engineer.
We have an existing high-fidelity, printable HTML/CSS invoice. We want to apply a specific refinement prompt to it.

Existing HTML:
${html}

Refinement Instruction:
${prompt}

Instructions:
1. Apply the user's refinement exactly. If they ask to change colors, change font, add columns, update bank details, change values, translate labels, format currencies, or restructure borders, execute it with pristine styling.
2. Ensure layout borders remain 100% proper, solid, and aligned. Apply explicit borders ('border: 1px solid #000;' or similar) to any newly introduced or modified table cells, and use 'border-collapse: collapse;' to ensure neat, crisp line intersections.
3. Keep the HTML highly printable and self-contained (all styles inside the head style block, no external assets or dependencies).
4. Preserve all other existing information, OCR structure, and metadata with 100% transcription accuracy unless directly requested to change.
5. Return ONLY the final updated HTML. Do NOT wrap the output in markdown code blocks like \`\`\`html or add any conversational introduction/conclusion. Return raw, executable updated HTML.`,
    });

    const generatedText = response.text || "";
    const cleanedHtml = cleanHtml(generatedText);
    res.json({ html: cleanedHtml });
  } catch (error: any) {
    console.error("Error refining invoice HTML with Gemini:", error);
    res.status(500).json({
      error: error.message || "An error occurred during AI refinement.",
    });
  }
});

// ---------------------------------------------------------------------------
// GET /api/health
// ---------------------------------------------------------------------------
app.get("/api/health", (_req: Request, res: Response) => {
  res.json({
    status: "ok",
    geminiConfigured: GEMINI_KEY_POOL.length > 0,
    keyPoolSize: GEMINI_KEY_POOL.length,
    activeKeyIndex: currentKeyIndex + 1,
    port: PORT,
  });
});

// ---------------------------------------------------------------------------
// 404 catch-all
// ---------------------------------------------------------------------------
app.use((_req: Request, res: Response) => {
  res.status(404).json({ error: "Not found" });
});

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Server started successfully. Running on http://localhost:${PORT}`);
  console.log(`Gemini key pool: ${GEMINI_KEY_POOL.length} key(s) configured.`);
  console.log(`  → Upload : http://localhost:${PORT}/upload`);
  console.log(`  → Editor : http://localhost:${PORT}/editor`);
  console.log(`  → Health : http://localhost:${PORT}/api/health`);
});

export default app;
