# Markdown Rendering in Chat Messages

Chat messages now support full Markdown formatting with GitHub Flavored Markdown (GFM) support.

## Supported Features

### Headers
All heading levels (H1-H6) are supported with proper sizing.

### Text Formatting
- **Bold text** with `**text**`
- *Italic text* with `*text*`
- ~~Strikethrough~~ with `~~text~~`
- `Inline code` with backticks

### Lists

**Unordered lists:**
- Item 1
- Item 2
  - Nested item 2.1
  - Nested item 2.2
- Item 3

**Ordered lists:**
1. First item
2. Second item
3. Third item

### Code Blocks

Inline code: `const greeting = "Hello";`

Code blocks:
```javascript
function greet(name) {
  return `Hello, ${name}!`;
}
```

```python
def calculate_score(data):
    return sum(data) / len(data)
```

### Blockquotes

> This is a blockquote.
> It can span multiple lines.

### Links

[Visit OpenAI](https://openai.com)

Links open in new tabs with security attributes.

### Tables

| Feature | Support | Notes |
|---------|---------|-------|
| Headers | ✅ | H1-H6 |
| Lists | ✅ | Ordered & Unordered |
| Code | ✅ | Inline & Blocks |
| Tables | ✅ | GFM Tables |

### Task Lists (GFM)

- [x] Completed task
- [ ] Pending task
- [ ] Another pending task

## Styling

- **User messages**: Inverted color scheme (white text on blue)
- **Assistant messages**: Dark text on white background
- **Code blocks**: Syntax-appropriate backgrounds
- **Links**: Properly colored with hover effects
- **Tables**: Responsive with proper borders

## Technical Details

**Libraries Used:**
- `react-markdown` - Main markdown rendering
- `remark-gfm` - GitHub Flavored Markdown support
- `@tailwindcss/typography` - Beautiful typography defaults

**Custom Styling:**
All markdown elements are styled to match the compact UI design with proper spacing and colors that adapt to user vs assistant messages.
