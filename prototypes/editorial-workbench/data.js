/* Fictional fixtures only. No network, real publisher or model is connected. */
"use strict";
const PULSE_DATA = {
  checkpoint: "2026-10-12T12:00:00Z",
  sources: [
    {
      id: "A",
      owner: "G1",
      health: "ok",
      complete: true,
      last: "14:55",
      restriction: ["عناوين وبيانات وصفية فقط", "Headlines and metadata only"],
    },
    {
      id: "B",
      owner: "G2",
      health: "stale",
      complete: false,
      last: "14:25",
      restriction: ["لا احتفاظ بالنص الكامل", "No full-text retention"],
    },
    {
      id: "C",
      owner: "G1",
      health: "ok",
      complete: true,
      last: "14:52",
      restriction: [
        "إعادة نشر؛ لا تُعدّ أصلًا مستقلًا",
        "Syndicated; not an independent origin",
      ],
    },
    {
      id: "D",
      owner: "G3",
      health: "ok",
      complete: true,
      last: "14:50",
      restriction: ["بيانات وصفية مع نسب المحتوى", "Metadata with attribution"],
    },
    {
      id: "E",
      owner: "G4",
      health: "ok",
      complete: true,
      last: "14:58",
      restriction: [
        "العناوين؛ التدريب غير مصرح به",
        "Headlines; no training permission",
      ],
    },
    {
      id: "F",
      owner: "G4",
      health: "limited",
      complete: false,
      last: "14:15",
      restriction: [
        "محاكاة توقف عند حد الطلبات",
        "Simulated stop at request limit",
      ],
    },
  ],
  events: [
    {
      id: "transport",
      beat: "transport",
      title: [
        "تجربة حافلات تربط مطارًا بأحياء جديدة في الرياض",
        "Airport shuttle pilot links new Riyadh neighborhoods",
      ],
      first: "05 Oct · 18:10",
      latest: [
        "ظهور خريطة مسارات أولية؛ التواتر وتاريخ التشغيل لم يُحسما.",
        "A draft route map appeared; service frequency and launch date remain unresolved.",
      ],
      what: [
        "في هذا السيناريو الخيالي، يدرس مشغّل نقل تجريبي ربط مطار بأحياء لا تغطيها الخدمة الحالية.",
        "In this fictional scenario, a transport operator is studying airport links for underserved neighborhoods.",
      ],
      relevance: [
        "زاوية خدمة عامة: هل تعالج المسارات فجوة الوصول للعاملين والمسافرين؟",
        "A public-service angle: would the routes close an access gap for workers and passengers?",
      ],
      unknown: [
        "لا يوجد تأكيد مستقل لتاريخ التشغيل أو الأجرة؛ الخريطة ليست جدولًا معتمدًا.",
        "No independent confirmation of fares or launch date; the map is not an approved timetable.",
      ],
      opportunity: [
        "تحقق من خطة التشغيل، وقارن زمن الرحلة وتكلفتها بالبدائل الحالية.",
        "Verify the operating plan and compare journey times and costs with existing alternatives.",
      ],
      recommendation: [
        "تحقق من الادعاء ثم فكّر في تقرير خدمي",
        "Verify the claim, then consider a service explainer",
      ],
      verification: "partial",
      initial: "new",
      series6: [1, 0, 1, 1, 2, 3],
      past24: [0, 0, 1, 0, 1, 0],
      days: [2, 1, 3, 2, 3, 5],
      potential: [
        "تصاعد محتمل في التغطية ضمن هذا السيناريو",
        "Potential coverage growth in this scenario",
      ],
      scenario: {
        6: [3, 4, 4],
        24: [5, 7, 9, 10],
        168: [10, 12, 14, 12, 10, 9, 7],
      },
      evidence: [
        [
          "A",
          "09:10",
          "original",
          "o1",
          [
            "مشغّل تجريبي يدرس ربط الأحياء بالمطار",
            "Pilot operator studies neighborhood airport links",
          ],
          [
            "وصف أولي للمشروع دون موعد تشغيل",
            "Initial project description, no launch date",
          ],
        ],
        [
          "C",
          "11:05",
          "syndicated",
          "o1",
          [
            "إعادة نشر تفاصيل الربط المقترح",
            "Proposed route details republished",
          ],
          [
            "صياغة مطابقة للمصدر A؛ ليست تأكيدًا مستقلًا",
            "Matches A; not independent confirmation",
          ],
        ],
        [
          "D",
          "12:15",
          "original",
          "o2",
          [
            "مقارنة نطاق التغطية مع الأحياء الطرفية",
            "Coverage compared with outer neighborhoods",
          ],
          [
            "مقارنة مستقلة؛ لا تؤكد الأسعار",
            "Independent comparison; does not confirm fares",
          ],
        ],
        [
          "A",
          "13:05",
          "original",
          "o1",
          ["مسودة خريطة مسارات التجربة", "Draft pilot route map"],
          [
            "خريطة أولية؛ تفاصيل التواتر مفقودة",
            "Draft map; frequency details missing",
          ],
        ],
        [
          "C",
          "13:35",
          "syndicated",
          "o1",
          ["تداول خريطة المسارات الأولية", "Draft route map circulated"],
          ["نقل عن A، دون أدلة إضافية", "Repeats A, no additional evidence"],
        ],
        [
          "A",
          "14:05",
          "original",
          "o1",
          [
            "الأسئلة التشغيلية ما زالت مفتوحة",
            "Operating questions remain open",
          ],
          ["لا تاريخ تشغيل مؤكد", "No confirmed launch date"],
        ],
        [
          "C",
          "14:20",
          "syndicated",
          "o1",
          ["إعادة عرض الأسئلة التشغيلية", "Operating questions recirculated"],
          ["إعادة نشر من الأصل نفسه", "Syndication from the same origin"],
        ],
        [
          "D",
          "14:40",
          "original",
          "o2",
          [
            "العاملون يحتاجون معلومات عن الرحلات المبكرة",
            "Workers need early-service details",
          ],
          [
            "زاوية وصول مستقلة؛ عينة توضيحية",
            "Independent access angle; illustrative sample",
          ],
        ],
      ],
    },
    {
      id: "technology",
      beat: "technology",
      title: [
        "اختبار تجريبي لمعيار أداء النماذج العربية",
        "Pilot benchmark tests Arabic model performance",
      ],
      first: "07 Oct · 18:40",
      latest: [
        "توسّع مجموعة مهام الاختبار؛ نتائج المقارنة لم تُراجع مستقلًا.",
        "Test tasks expanded; comparative results lack independent review.",
      ],
      what: [
        "فريق بحثي خيالي يختبر نماذج عربية على مهام لغوية محلية.",
        "A fictional research team tests Arabic models on locally relevant language tasks.",
      ],
      relevance: [
        "يساعد شرح منهجية الاختبار على تجنب تحويل نتيجة محدودة إلى ادعاء تفوق شامل.",
        "Explaining the methodology helps prevent narrow results becoming broad superiority claims.",
      ],
      unknown: [
        "حجم العينة وتسرب بيانات التدريب وقابلية إعادة الاختبار غير مؤكدة.",
        "Sample size, training leakage and reproducibility remain unverified.",
      ],
      opportunity: [
        "اطلب وصف البيانات ومنهجية التقييم ورأي باحث مستقل قبل المقارنة.",
        "Request dataset details, evaluation methods and independent review before comparing models.",
      ],
      recommendation: [
        "اطلب التحقق من المنهجية",
        "Request methodology verification",
      ],
      verification: "unverified",
      initial: "verify",
      series6: [0, 1, 0, 1, 1, 2],
      past24: [0, 1, 0, 0, 1, 0],
      days: [0, 0, 1, 1, 2, 2],
      potential: [
        "متابعة محدودة بالأدلة المتاحة",
        "Watch within available evidence",
      ],
      scenario: { 6: [2, 2, 3], 24: [3, 4, 5, 6], 168: [6, 7, 5, 6, 4, 3, 3] },
      evidence: [
        [
          "A",
          "10:05",
          "original",
          "o3",
          ["مهام جديدة للاختبار العربي", "New Arabic benchmark tasks"],
          ["وصف منهجي أولي", "Preliminary methodology"],
        ],
        [
          "B",
          "12:20",
          "syndicated",
          "o3",
          ["توسيع قائمة مهام الاختبار", "Benchmark task list expands"],
          ["تغذية متأخرة؛ اكتمال مجهول", "Delayed feed; completeness unknown"],
        ],
        [
          "E",
          "13:30",
          "unknown",
          null,
          ["قراءة في نتائج النماذج", "A reading of model results"],
          ["أصل التقرير غير محسوم", "Reporting origin unresolved"],
        ],
        [
          "A",
          "14:10",
          "original",
          "o3",
          [
            "فريق الاختبار يوضح حدود العينة",
            "Testing team explains sample limits",
          ],
          ["لم تتوفر مراجعة مستقلة", "No independent review"],
        ],
        [
          "B",
          "14:25",
          "syndicated",
          "o3",
          ["نقل توضيح حدود الاختبار", "Test limitations republished"],
          [
            "وقت رصد خيالي محفوظ رغم التأخر",
            "Stored fictional observation despite delay",
          ],
        ],
      ],
    },
    {
      id: "sport",
      beat: "sport",
      title: [
        "تعديل تجريبي لجدول بطولة شبابية في جدة",
        "Youth tournament schedule changes in Jeddah",
      ],
      first: "05 Oct · 18:55",
      latest: [
        "مسودة جديدة تفصل بعض المباريات المسائية؛ أماكن اللعب غير محسومة.",
        "A new draft separates evening matches; venues remain unresolved.",
      ],
      what: [
        "بطولة شبابية خيالية تراجع جدول المباريات بعد ملاحظات الأندية.",
        "A fictional youth tournament revises its schedule after club feedback.",
      ],
      relevance: [
        "التغيير قد يؤثر على تنقل اللاعبين والأسر، وليس مجرد إعادة نشر جدول.",
        "The change could affect player and family travel, beyond a timetable rewrite.",
      ],
      unknown: [
        "الحجز النهائي للملاعب وإجراءات إخطار الأندية لم يُتحقق منهما.",
        "Final venue bookings and club notification are unverified.",
      ],
      opportunity: [
        "قارن النسختين واسأل عن أثر التغيير على الأندية الزائرة.",
        "Compare versions and ask how visiting clubs are affected.",
      ],
      recommendation: [
        "راقب اكتمال الجدول",
        "Watch for the finalized schedule",
      ],
      verification: "partial",
      initial: "watch",
      series6: [0, 1, 1, 0, 2, 0],
      past24: [0, 1, 1, 0, 0, 0],
      days: [1, 1, 2, 3, 2, 3],
      potential: ["استمرار محدود للتغطية", "Limited coverage continuation"],
      scenario: { 6: [1, 1, 2], 24: [2, 3, 3, 4], 168: [4, 5, 5, 3, 2, 2, 1] },
      evidence: [
        [
          "C",
          "10:10",
          "syndicated",
          "o4",
          ["مسودة جدول البطولة", "Draft tournament schedule"],
          [
            "إعادة نشر؛ الأصل غير ضمن اللوحة",
            "Syndication; origin outside panel",
          ],
        ],
        [
          "E",
          "11:15",
          "original",
          "o5",
          ["أثر الجدول على تنقل الأندية", "Schedule impact on club travel"],
          [
            "رأي أندية خيالية؛ لا تأكيد للملاعب",
            "Fictional clubs; venues not confirmed",
          ],
        ],
        [
          "C",
          "13:05",
          "syndicated",
          "o4",
          ["مواعيد مسائية في المسودة الجديدة", "Evening slots in new draft"],
          ["النقل من الأصل نفسه", "Same originating report"],
        ],
        [
          "E",
          "13:30",
          "original",
          "o5",
          ["الأسر تنتظر تأكيد المكان", "Families await venue confirmation"],
          ["زاوية خدمة للجمهور المحلي", "Local service angle"],
        ],
      ],
    },
    {
      id: "culture",
      beat: "culture",
      title: [
        "صالات سينما مستقلة تراجع إمكانية الوصول",
        "Independent cinemas review accessibility",
      ],
      first: "05 Oct · 17:30",
      latest: [
        "قائمة أولية بتحسينات الوصول؛ مواقع التنفيذ والميزانية غير معلنة.",
        "A preliminary accessibility list appears; locations and budget are missing.",
      ],
      what: [
        "شبكة سينما خيالية تدرس تحسين وصول ذوي الإعاقة إلى العروض.",
        "A fictional cinema network studies accessibility improvements.",
      ],
      relevance: [
        "زاوية مساءلة خدمية تركز على تجربة الزائر بدل تكرار الوصف الترويجي.",
        "A service-accountability angle focused on visitor experience rather than promotional copy.",
      ],
      unknown: [
        "نطاق التحسينات ومدى إشراك المستخدمين في الاختبار غير معروفين.",
        "Improvement scope and user participation in testing are unknown.",
      ],
      opportunity: [
        "قابل مستخدمين ومتخصصي وصول، واطلب معايير قابلة للتحقق.",
        "Interview users and accessibility specialists; request verifiable standards.",
      ],
      recommendation: ["فكّر في تقرير تفسيري", "Consider an explainer"],
      verification: "unverified",
      initial: "new",
      series6: [1, 0, 0, 1, 0, 1],
      past24: [1, 0, 0, 1, 0, 1],
      days: [1, 2, 2, 1, 2, 3],
      potential: ["الأدلة غير مكتملة", "Evidence incomplete"],
      scenario: { 6: [1, 1, 1], 24: [2, 2, 3, 3], 168: [3, 4, 5, 4, 3, 2, 2] },
      evidence: [
        [
          "B",
          "09:30",
          "original",
          "o6",
          [
            "مقترحات وصول لصالات مستقلة",
            "Access proposals for independent cinemas",
          ],
          ["تغطية ناقصة بسبب التأخر", "Incomplete coverage due to delay"],
        ],
        [
          "D",
          "12:35",
          "original",
          "o7",
          [
            "معايير الوصول تحتاج تجربة مستخدم",
            "Accessibility needs user testing",
          ],
          [
            "تحليل مستقل، لا زيارات موثقة",
            "Independent analysis, no documented visits",
          ],
        ],
        [
          "F",
          "14:15",
          "syndicated",
          "o6",
          ["إعادة نشر قائمة التحسينات", "Improvement list republished"],
          [
            "حد طلبات؛ ملاحظات تاريخية محفوظة",
            "Rate limit; historical observations retained",
          ],
        ],
      ],
    },
    {
      id: "economy",
      beat: "economy",
      title: [
        "منشآت صغيرة تراجع تكلفة الموردين",
        "Small businesses review supplier costs",
      ],
      first: "05 Oct · 16:20",
      latest: [
        "مسح خيالي لثلاث منشآت يكشف اختلاف التكاليف حسب المدخلات.",
        "A fictional three-business survey shows input-specific cost differences.",
      ],
      what: [
        "منشآت خيالية تقارن عروض الموردين وتراجع خيارات الشراء المشترك.",
        "Fictional businesses compare supplier offers and joint purchasing options.",
      ],
      relevance: [
        "تقرير تفسيري قد يوضح إدارة التكلفة دون تعميم عينة صغيرة على الاقتصاد.",
        "An explainer can clarify cost management without generalizing a tiny sample to the economy.",
      ],
      unknown: [
        "العينة غير ممثلة؛ لا يمكن استنتاج اتجاه اقتصادي عام منها.",
        "The sample is not representative and cannot establish an economy-wide trend.",
      ],
      opportunity: [
        "تحقق من الفواتير وقارن مدخلات متشابهة واذكر حدود العينة.",
        "Verify invoices, compare like inputs and disclose sample limitations.",
      ],
      recommendation: [
        "التغطية كافية للزاوية الحالية؛ راقب تغيرًا جديدًا",
        "Current angle covered sufficiently; watch for material change",
      ],
      verification: "partial",
      initial: "assigned",
      editor: "sara",
      series6: [1, 1, 0, 1, 1, 0],
      past24: [1, 0, 1, 0, 1, 1],
      days: [3, 2, 4, 3, 4, 5],
      potential: [
        "استمرار للتغطية؛ دون إشارة مستقلة",
        "Coverage continuation; no independent signal",
      ],
      scenario: { 6: [1, 1, 2], 24: [2, 3, 3, 4], 168: [4, 4, 5, 5, 3, 2, 2] },
      evidence: [
        [
          "A",
          "09:05",
          "original",
          "o8",
          ["مقارنة عروض موردين", "Supplier offers compared"],
          ["ثلاث منشآت خيالية فقط", "Only three fictional businesses"],
        ],
        [
          "E",
          "10:20",
          "original",
          "o9",
          ["خيارات شراء مشترك للمنشآت", "Joint procurement options"],
          [
            "رواية مستقلة محدودة بالعينة",
            "Independent report with limited sample",
          ],
        ],
        [
          "A",
          "12:40",
          "original",
          "o8",
          ["اختلاف التكاليف حسب المدخلات", "Costs vary by input"],
          ["ليست بيانات اقتصاد كلي", "Not macroeconomic data"],
        ],
        [
          "E",
          "13:35",
          "original",
          "o9",
          [
            "الفواتير تحتاج مقارنة منضبطة",
            "Invoices need like-for-like comparison",
          ],
          ["عينة غير ممثلة", "Nonrepresentative sample"],
        ],
      ],
    },
  ],
};
