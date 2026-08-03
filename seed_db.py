"""Seed the admin DB tables from existing knowledge-base.md and spec.json."""

import json
from pathlib import Path
from database import (
    init_db, upsert_faq, upsert_course, upsert_section, upsert_rule,
    get_all_courses, get_all_sections,
)

BASE_DIR = Path(__file__).resolve().parent


def seed():
    init_db()

    # Skip if already seeded
    if get_all_courses() or get_all_sections():
        print("DB already has content — skipping seed.")
        return

    print("Seeding DB from existing files...")

    # ── Content sections ──
    upsert_section("about", "על השיטה",
        "שיטת שרמן (קיימת מאז 2004) באה מתחום הבריאות הטבעית והרפואה המונעת.\n"
        "מאפשרת להכיר את הגוף, מעודדת החזרה של הווסת למסלולה הטבעי והגברת החיבור לתבונה הנשית.\n\n"
        "תוצאות שנשים חוות:\n"
        "- קיצור משך ימי הדימום\n"
        "- הקלה משמעותית בכאב\n"
        "- שימוש מופחת בפדים וטמפונים\n"
        "- הקלה בתופעות קדם וסתיות (PMS)\n\n"
        "איך? באמצעות ידע וכלים פרקטיים - בלי כדורים, בלי טיפולים חיצוניים.\n"
        "כולל תרגול פיזי + שינוי תפיסתי + התרוקנות מודעת תוך שמירה על רצפת האגן.")

    upsert_section("syllabus", "סילבוס (6 פרקים)",
        "פרק 1: המערכת הנשית - הכרות אינטימית עם המערכת הנשית, תבונת הגוף, תפקיד האיברים.\n"
        "פרק 2: התהליך המחזורי - ביוץ, הכנה להריון, שחרור רירית הרחם.\n"
        "פרק 3: מה נשים היו עושות פעם - מסע בזמן לתקופה בה ההתנהלות עם הווסת הייתה טבעית.\n"
        "פרק 4: כלים פרקטיים לווסת קלה - התרוקנות מודעת, שמירה על רצפת האגן.\n"
        "פרק 5: הקלה בכאב - כלים בהשראת עולם הלידה, שפת הכאב, מעגל הכאב.\n"
        "פרק 6: הקלה על תופעות קדם וסתיות - התבוננות מחדש, מעקב אחרי המחזוריות.")

    upsert_section("fam", "מודעות לפוריות (FAM) - עם אבישג מאיה זלוף",
        "שיטה בדוקה מדעית למניעת או תכנון הריון באופן טבעי, בלי הורמונים.\n"
        "מעקב אחר 3 סימנים ללמוד מתי הימים הפוריים.\n\n"
        "תוכן: מערכת הרבייה, סימני פוריות, מעקב יומיומי, מצבי בריאות, מיניות, תזונה נשית.\n\n"
        "לתשומת לב: צריך מד חום מיוחד + גישה למדפסת. למניעת הריון - חשוב ליווי מאבישג.")

    upsert_section("mothers_daughters", "קורס אמהות ונערות",
        "7 מפגשים בני שעה, בשפה ובתכנים לנערות.\n"
        "אמא מוזמנת להצטרף (מומלץ!).\n"
        "השיעור הראשון פתוח לכולן בחינם.\n\n"
        "תוצאות: קשר טוב יותר עם הגוף, הקלה בכאבים, קיצור ימים, פחות סירבול, הקלה ב-PMS.")

    upsert_section("frontal", "קורסים פרונטליים",
        "מתקיימים בתדירות לא גבוהה כרגע.\n"
        "אבן יהודה - הצטרפות לצ'אט עדכונים במייל\n"
        "ירושלים - הצטרפות לצ'אט עדכונים במייל\n"
        "באזור מגורים - אפשרי אם יש יכולת לארגן קבוצה. מייל: meiravsherman.ans@gmail.com")

    upsert_section("personal", "שיחה אישית",
        "שיחה אישית עם מירב - ללא עלות.\n"
        "ליווי וטיפולים אישיים בזום ובאבן יהודה.\n"
        "נושאים: תסמיני ווסת, פוריות, מיניות - בהתאם לגישת השיטה.")

    upsert_section("policies", "מדיניות",
        "ביטולים: 14 יום מיום הרכישה.\n"
        "קורסים דיגיטליים: לשימוש אישי, ללא הגבלת זמן.\n"
        "אינטרנט כשר: כל הקורסים זמינים גם בדרייב.")

    upsert_section("contact", "פרטי קשר",
        "מייל: meiravsherman.ans@gmail.com\n"
        "מספר מירב: 050-318-9636")

    upsert_section("coupon", "הנחות וקודי קופון",
        "קוד קופון: SHERI = 36% הנחה על כל הקורסים הדיגיטליים (לכבוד השקת הבוטית).")

    # ── Courses ──
    courses_data = [
        {"name": "שרמן לנשים - יסודות שיטת שרמן", "price": "540₪", "audience": "להכיר את הגוף ולהקל על תסמיני הווסת", "chapters": "1-4", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/ZDEWTNePuEmXz45sietjg"},
        {"name": "יסודות + הקלה בכאבים", "price": "675₪", "audience": "למי שרוצה גם להקל על כאבי וסת עזים", "chapters": "1-5", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/WZfTZBhf0CoIgmbmqas4A"},
        {"name": "הקלה בתופעות קדם וסתיות", "price": "220₪", "audience": "להקל על תופעות קדם וסתיות", "chapters": "6", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/lqRXZwNTMECbKSYUwJo9Fg"},
        {"name": "קורס הדגל של שיטת שרמן (מארז)", "price": "1,184₪", "audience": "הכל ביחד - הכרת הגוף, הקלה, התרוקנות מודעת, כאבים, PMS", "chapters": "1-6", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/FSXoJKJkt0CloMmTU6epw"},
        {"name": "מיני קורס להתרוקנות מודעת", "price": "297₪", "audience": "קצר וממוקד, נקודתי ותמציתי", "chapters": "-", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/6UQeilvBPkic5D5tAL6QQ"},
        {"name": "קורס הדגל + מודעות לפוריות", "price": "1,250₪", "audience": "הכל + מודעות לפוריות", "chapters": "1-6 + FAM", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/auUQ7m0J80WxJNMqHgdwEg"},
        {"name": "מודעות לפוריות (בנפרד)", "price": "350₪", "audience": "מניעת/תכנון הריון באופן טבעי", "chapters": "FAM", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/lqRXZwNTMECbKSYUwJo9Fg"},
        {"name": "קורס שרמן לאמהות ונערות", "price": "1,250₪", "audience": "אמא ובת ללמוד ביחד", "chapters": "7 מפגשים", "purchase_url": "https://secure.cardcom.solutions/EA/EA5/zBeZWXVU0G6GMHCKdng4Q"},
    ]
    for i, c in enumerate(courses_data):
        upsert_course(None, name=c["name"], price=c["price"], audience=c["audience"],
                      chapters=c["chapters"], purchase_url=c["purchase_url"], sort_order=i)

    # ── Rules (from spec.json behavioral_rules) ──
    spec_path = BASE_DIR / "spec.json"
    if spec_path.exists():
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        rules = spec.get("behavioral_rules", {})
        rule_titles = {
            "rule_1_service_guard": "שמירה שירותית",
            "rule_2_human_intervention": "התערבות אנושית",
            "rule_3_pain_empathy": "אמפתיה לכאב",
            "rule_4_payment_deferral": "דחיית תשלום",
            "rule_5_opt_in_recognition": "זיהוי מדוורות",
            "rule_6_closure_words": "כיבוד סירוב",
            "rule_7_active_leading": "הובלה אקטיבית",
            "rule_8_follow_up": "פולואפ",
        }
        for key, body in rules.items():
            title = rule_titles.get(key, key)
            upsert_rule(key, title, body)

    print(f"Seeded: {len(courses_data)} courses, {len(rules)} rules, 9 content sections.")
    print("FAQ is empty — Merav will add via admin panel.")


if __name__ == "__main__":
    seed()
