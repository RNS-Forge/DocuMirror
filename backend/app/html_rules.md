# HTML and EJS Template Rules for DocuMirror Generation

When generating or extracting layout for DocuMirror HTML/EJS templates, you must STRICTLY adhere to the following permitted tags, classes, and structures. Do NOT invent new CSS classes or use unlisted HTML tags.

## 1. Allowed HTML Tags
### Document Structure
- `<!DOCTYPE html>`, `<html>`, `<head>`, `<meta>`, `<title>`, `<body>`

### Table Structure (Crucial for layouts)
- `<table>`, `<colgroup>`, `<col>`, `<tr>`, `<td>`, `<th>`
- Use `colspan="X"` and `rowspan="X"` where columns or rows are visually merged in the source document.

### Text Formatting & Divisions
- `<span>`, `<br>`, `<strong>`, `<b>`, `<u>`, `<div>`

## 2. Allowed CSS Classes
### Styling Classes
- `.title` (Centered, bold title)
- `.bold` (Bold text)
- `.center` (Center-aligned text)
- `.right` (Right-aligned text)

### Border Classes and Accuracy
You must replicate the exact borders seen in the original image. By default tables should have borders if the image has them. If specific sides lack borders, use:
- `.no-border` (No border on all sides)
- `.no-border-bottom` (No bottom border)
- `.no-border-top` (No top border)
- `.no-border-right` (No right border)
- `.no-border-left` (No left border)
If custom border styling is needed to perfectly match the image (e.g., thick borders, double borders), you may use inline styles `style="border: 2px solid black;"` or similar.

## 3. Allowed Inline Styles
Only use the following inline styles when absolutely necessary to achieve 100% accuracy:
- `style="width: X%;"` (Column width)
- `style="text-align: left/center/right;"`
- `style="padding: Xpx;"`
- `style="vertical-align: top/bottom;"`
- `style="word-wrap: break-word;"`
- `style="text-decoration: underline;"`
- `style="height: Xpx;"`

## 4. Embedded JavaScript (Template Tags) & Conditional Logic
You MUST use EJS to dynamically render data, respecting relationships, groupings, and calculations.
- **Loops**: Use loops ONLY if there are list items. 
  `<% if (docs.listOfItems && docs.listOfItems.length > 0) { %>`
  `<% docs.listOfItems.forEach(function(item) { %> ... <% }) %>`
  `<% } %>`
- **Conditionals for Totals/Calculations**: If the document contains subtotals, totals, or calculations, only render them if they exist in the data:
  `<% if (docs.subTotal) { %><tr><td>Sub Total</td><td><%= docs.subTotal %></td></tr><% } %>`
  `<% if (docs.total) { %><tr><td>Total</td><td><%= docs.total %></td></tr><% } %>`
- **Group By**: If the items in the image are grouped by category or have section headers, structure your JSON to support groups and use nested loops:
  `<% docs.groups.forEach(function(group) { %> ... loop over group.items ... <% }) %>`
- **Logic**: `<%- ... %>` (Unescaped output for HTML like `<br>`), `<%= ... %>` (Escaped output for variables).
- **Functions**: `<% function formatDate(dateInput) { ... } %>`, `<% function addressLine() { ... } %>`

## 5. Dynamic Variables and Schema Relationships
All variables MUST be prefixed with `docs.` (e.g., `docs.invoiceNumber`, `docs.exporterName`, `docs.listOfItems`).
If the image has advanced structures (subtotals, tax calculations, grouped items), you must invent the appropriate `docs.` variables to represent them and accurately map the EJS logic to output them.
