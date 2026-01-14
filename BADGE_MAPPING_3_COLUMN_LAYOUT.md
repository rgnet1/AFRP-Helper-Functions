# Badge Mapping 3-Column Layout Update

## Overview
Restructured the Badge Template Mapping page from a 2-column layout to a 3-column layout with saved templates moved to a left sidebar for better UX and consistency with the Preprocessing Designer.

## Changes Made

### Layout Structure

**Before (2 columns):**
```
+----------------------------------+----------------------------------+
|    Template Configuration        |    Column Mapping                |
+----------------------------------+----------------------------------+
|                                                                     |
|                    Saved Templates (Full Width)                     |
+---------------------------------------------------------------------+
```

**After (3 columns):**
```
+-----------+----------------------------------+----------------------------------+
| Saved     |    Template Configuration        |    Column Mapping                |
| Templates |                                  |                                  |
| (Sidebar) |                                  |                                  |
+-----------+----------------------------------+----------------------------------+
```

### CSS Updates

#### New Styles Added
1. **Main Content Container**
   - Grid layout: `280px 1fr`
   - Creates space for sidebar + main content

2. **Sidebar**
   - Width: `280px`
   - Sticky positioning: stays visible while scrolling
   - White background with shadow
   - Border-radius for modern look

3. **Sidebar Template List**
   - Scrollable with max-height
   - Custom green-themed scrollbar
   - Hover effects on items
   - Active state highlighting

4. **Template Items**
   - Compact design
   - Hover: slides right slightly
   - Active: green background
   - Delete button appears on hover

5. **New Template Button**
   - Full-width green button
   - Located at bottom of sidebar
   - Matches application theme

### Responsive Design

#### Breakpoints
- **≤ 1400px**: Sidebar reduces to `250px`
- **≤ 1200px**: Main grid becomes single column (stacks Template Config and Column Mapping)
- **≤ 900px**: Full single column (sidebar on top)

### JavaScript Updates

#### Updated Functions
1. **`loadSavedTemplates()`**
   - Now populates `sidebarTemplatesList` instead of `savedTemplates`
   - Uses compact sidebar item styling
   - Shows active state for currently loaded template

2. **Event Listeners**
   - Added listener for `sidebarNewTemplateBtn`
   - Connected to existing `resetForm()` function

#### Template Item Format
```javascript
<li class="sidebar-template-item ${active ? 'active' : ''}" onclick="loadTemplate(id)">
    <span>Template Name</span>
    <button class="delete-btn">
        <i class="fas fa-trash"></i>
    </button>
</li>
```

## Benefits

### 1. **Better Organization**
- Templates always visible in sidebar
- No need to scroll down to see saved templates
- Quick access to any template

### 2. **More Screen Space**
- Main content area can use full width
- Better for editing complex mappings
- Reduced vertical scrolling

### 3. **Consistency**
- Matches Preprocessing Designer layout
- Familiar UX across both template pages
- Same sidebar interaction pattern

### 4. **Improved Workflow**
- Easy template switching
- Visual indication of active template
- Quick "New Template" access

### 5. **Modern Design**
- Sticky sidebar stays in view
- Smooth transitions and hover effects
- Custom scrollbar styling
- Responsive on all screen sizes

## Technical Details

### HTML Structure
```html
<div class="main-content">
    <!-- Left Sidebar -->
    <div class="sidebar">
        <h2>Saved Templates</h2>
        <ul class="sidebar-templates-list">
            <!-- Template items here -->
        </ul>
        <button class="new-template-btn">New Template</button>
    </div>
    
    <!-- Main Grid (2 columns) -->
    <div class="main-grid">
        <div class="card">Template Configuration</div>
        <div class="card">Column Mapping</div>
    </div>
</div>
```

### CSS Grid
```css
.main-content {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 20px;
}

.main-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
}
```

### Sticky Positioning
```css
.sidebar {
    position: sticky;
    top: 20px;
    height: fit-content;
}
```

## Files Modified

- `templates/badge_mapping.html`:
  - Updated CSS for 3-column layout
  - Added sidebar styles
  - Added responsive media queries
  - Updated HTML structure
  - Modified `loadSavedTemplates()` function
  - Added event listener for sidebar button

## User Experience

### Before
1. User scrolls to bottom to see saved templates
2. Clicks template
3. Scrolls back up to edit

### After
1. Templates always visible in left sidebar
2. Click template (no scrolling)
3. Edit immediately in main area
4. Template list stays visible

## Visual Polish

- **Green Theme**: All colors match application theme
- **Smooth Transitions**: 0.2s transitions on hover
- **Custom Scrollbar**: Green-themed scrollbar in sidebar
- **Active Indicator**: Selected template highlighted in green
- **Hover Effects**: Subtle slide animation on hover
- **Delete on Hover**: Delete button appears when hovering over template

## Testing Checklist

✅ Page loads successfully
✅ Saved templates appear in sidebar
✅ Template selection works
✅ Active template highlighted
✅ New Template button works
✅ Delete button appears on hover
✅ Sidebar scrolls with many templates
✅ Sticky positioning works
✅ Responsive on smaller screens
✅ Green theme consistent throughout

## Conclusion

The 3-column layout provides a significantly better user experience by:
- Keeping templates always accessible
- Maximizing editing space
- Maintaining visual consistency
- Supporting responsive design

The sidebar pattern matches the Preprocessing Designer, creating a consistent experience across both template management pages.
