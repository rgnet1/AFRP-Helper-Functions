# Avery 5392 Layout Fix

## ✅ What I Fixed

Based on your image showing the actual Avery 5392 label layout:

### **Old Configuration** ❌
- 2 columns × 2 rows = **4 badges per sheet**
- Incorrect layout

### **New Configuration** ✅
- **2 columns × 3 rows = 6 badges per sheet**
- Each badge: 3" wide × 4" tall (portrait)
- Matches your Avery 5392 sheets!

---

## 📐 Layout Details

```
Page: 8.5" × 11" (Letter size)

┌─────────────────────────────────────┐
│                                     │
│  ┌───────┐      ┌───────┐          │  ← Row 1
│  │ 3"×4" │      │ 3"×4" │          │
│  │       │      │       │          │
│  └───────┘      └───────┘          │
│                                     │
│  ┌───────┐      ┌───────┐          │  ← Row 2
│  │ 3"×4" │      │ 3"×4" │          │
│  │       │      │       │          │
│  └───────┘      └───────┘          │
│                                     │
│  ┌───────┐      ┌───────┐          │  ← Row 3
│  │ 3"×4" │      │ 3"×4" │          │
│  │       │      │       │          │
│  └───────┘      └───────┘          │
│                                     │
└─────────────────────────────────────┘

6 badges per sheet
2 columns × 3 rows
```

---

## 🧪 Test the New Layout

1. **Generate badges** using your existing template
2. **Print ONE test sheet** on Avery 5392 labels
3. **Check alignment**:
   - Should have 6 badges (not 4 or 8)
   - Badges should align with the Avery label pockets
   - All 6 positions filled

---

## 🔧 If Alignment Is Off

The margins are currently set to:
- **Left margin**: 1.25"
- **Top margin**: -0.5" (negative to start higher on page)
- **Horizontal gap**: 0" (no gap between columns)
- **Vertical gap**: 0" (no gap between rows)

If badges don't align with your Avery sheets, I can adjust these values. Just tell me:
- Are badges **too high** or **too low**?
- Are badges **too far left** or **too far right**?
- Do you need **more** or **less** space between columns?
- Do you need **more** or **less** space between rows?

---

## 📝 Current Status

✅ Container rebuilt with new layout
✅ System configured for 6 badges per sheet
✅ Ready to test

---

## 🚀 Next Steps

1. Go to http://localhost:5066/badges-v2
2. Generate badges with your existing template
3. Print **ONE test sheet** on Avery 5392 labels
4. Check if badges align with label pockets
5. Let me know if adjustments are needed!

---

**Note**: The badges themselves are still in **portrait orientation** (3" wide × 4" tall) as shown in your image. If you want the content INSIDE each badge to be landscape-oriented, we can rotate the SVG template, but the label slots themselves are portrait on Avery 5392.
