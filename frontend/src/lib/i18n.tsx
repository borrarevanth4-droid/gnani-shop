"use client";

// Interface text in Gnani's 10 languages. The buyer's choice here is also
// sent with typed chat, so the agent replies in it; on a voice turn Gnani's
// own language detection takes over (and updates this, so the screen follows
// the conversation).

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type LangCode = "en-IN" | "hi-IN" | "ta-IN" | "te-IN" | "kn-IN" | "ml-IN" | "mr-IN" | "bn-IN" | "gu-IN" | "pa-IN";

export const LANGUAGES: { code: LangCode; native: string; english: string }[] = [
  { code: "en-IN", native: "English", english: "English" },
  { code: "hi-IN", native: "हिन्दी", english: "Hindi" },
  { code: "ta-IN", native: "தமிழ்", english: "Tamil" },
  { code: "te-IN", native: "తెలుగు", english: "Telugu" },
  { code: "kn-IN", native: "ಕನ್ನಡ", english: "Kannada" },
  { code: "ml-IN", native: "മലയാളം", english: "Malayalam" },
  { code: "mr-IN", native: "मराठी", english: "Marathi" },
  { code: "bn-IN", native: "বাংলা", english: "Bengali" },
  { code: "gu-IN", native: "ગુજરાતી", english: "Gujarati" },
  { code: "pa-IN", native: "ਪੰਜਾਬੀ", english: "Punjabi" },
];

type Key =
  | "shop" | "dashboard" | "orders" | "agent" | "wallet" | "voiceLab"
  | "heroTitle" | "heroSub" | "tapToSpeak" | "listening" | "thinking" | "speaking" | "tapToStop"
  | "typeInstead" | "send" | "youSaid" | "cart" | "total" | "emptyCart" | "add" | "buyNow"
  | "payWallet" | "payCod" | "confirm" | "decline" | "needsTap" | "balance" | "demoMoney"
  | "search" | "realtime" | "pushToTalk" | "voice" | "language" | "underTheHood" | "newChat"
  | "signOut" | "orderPlaced" | "codPlaced" | "inStock" | "outOfStock";

const T: Record<LangCode, Record<Key, string>> = {
  "en-IN": {
    shop: "Shop", dashboard: "Dashboard", orders: "Orders", agent: "My Agent", wallet: "Wallet", voiceLab: "Voice Lab",
    heroTitle: "Just say what you need.",
    heroSub: "Speak in any of 10 Indian languages. Gnani understands, our shop assistant fills your cart, and nothing is paid until you tap.",
    tapToSpeak: "Tap to speak", listening: "Listening…", thinking: "Thinking…", speaking: "Speaking…", tapToStop: "Tap to stop",
    typeInstead: "Type instead", send: "Send", youSaid: "You said", cart: "Cart", total: "Total", emptyCart: "Your cart is empty",
    add: "Add", buyNow: "Buy now", payWallet: "Pay with Wallet", payCod: "Cash on Delivery", confirm: "Confirm",
    decline: "Decline", needsTap: "Needs your tap", balance: "Balance", demoMoney: "demo money", search: "Search products",
    realtime: "Live conversation", pushToTalk: "Push to talk", voice: "Voice", language: "Language",
    underTheHood: "Under the hood", newChat: "New chat", signOut: "Sign out", orderPlaced: "Order placed",
    codPlaced: "Order placed — pay cash on delivery", inStock: "In stock", outOfStock: "Out of stock",
  },
  "hi-IN": {
    shop: "दुकान", dashboard: "डैशबोर्ड", orders: "ऑर्डर", agent: "मेरा एजेंट", wallet: "वॉलेट", voiceLab: "वॉइस लैब",
    heroTitle: "बस बोलिए, क्या चाहिए।",
    heroSub: "10 भारतीय भाषाओं में से किसी में भी बोलिए। Gnani समझता है, हमारा सहायक कार्ट भरता है, और आपके टैप के बिना कोई भुगतान नहीं होता।",
    tapToSpeak: "बोलने के लिए टैप करें", listening: "सुन रहे हैं…", thinking: "सोच रहे हैं…", speaking: "बोल रहे हैं…", tapToStop: "रोकने के लिए टैप करें",
    typeInstead: "टाइप करें", send: "भेजें", youSaid: "आपने कहा", cart: "कार्ट", total: "कुल", emptyCart: "आपका कार्ट खाली है",
    add: "जोड़ें", buyNow: "अभी खरीदें", payWallet: "वॉलेट से भुगतान", payCod: "कैश ऑन डिलीवरी", confirm: "पुष्टि करें",
    decline: "रद्द करें", needsTap: "आपका टैप चाहिए", balance: "बैलेंस", demoMoney: "डेमो राशि", search: "उत्पाद खोजें",
    realtime: "लाइव बातचीत", pushToTalk: "दबाकर बोलें", voice: "आवाज़", language: "भाषा",
    underTheHood: "अंदर क्या हुआ", newChat: "नई बातचीत", signOut: "साइन आउट", orderPlaced: "ऑर्डर हो गया",
    codPlaced: "ऑर्डर हो गया — डिलीवरी पर नकद दें", inStock: "स्टॉक में", outOfStock: "स्टॉक खत्म",
  },
  "ta-IN": {
    shop: "கடை", dashboard: "டாஷ்போர்டு", orders: "ஆர்டர்கள்", agent: "என் ஏஜென்ட்", wallet: "வாலெட்", voiceLab: "வாய்ஸ் லேப்",
    heroTitle: "என்ன வேண்டும் என்று சொல்லுங்கள்.",
    heroSub: "10 இந்திய மொழிகளில் எதிலும் பேசுங்கள். Gnani புரிந்துகொள்கிறது, உதவியாளர் கார்ட்டை நிரப்புகிறார், நீங்கள் தட்டும் வரை பணம் செலுத்தப்படாது.",
    tapToSpeak: "பேச தட்டவும்", listening: "கேட்கிறது…", thinking: "யோசிக்கிறது…", speaking: "பேசுகிறது…", tapToStop: "நிறுத்த தட்டவும்",
    typeInstead: "தட்டச்சு செய்", send: "அனுப்பு", youSaid: "நீங்கள் சொன்னது", cart: "கார்ட்", total: "மொத்தம்", emptyCart: "உங்கள் கார்ட் காலியாக உள்ளது",
    add: "சேர்", buyNow: "இப்போது வாங்கு", payWallet: "வாலெட்டில் செலுத்து", payCod: "கேஷ் ஆன் டெலிவரி", confirm: "உறுதிசெய்",
    decline: "நிராகரி", needsTap: "உங்கள் தட்டல் தேவை", balance: "இருப்பு", demoMoney: "டெமோ பணம்", search: "பொருட்களைத் தேடு",
    realtime: "நேரடி உரையாடல்", pushToTalk: "அழுத்திப் பேசு", voice: "குரல்", language: "மொழி",
    underTheHood: "உள்ளே என்ன நடந்தது", newChat: "புதிய உரையாடல்", signOut: "வெளியேறு", orderPlaced: "ஆர்டர் செய்யப்பட்டது",
    codPlaced: "ஆர்டர் செய்யப்பட்டது — டெலிவரியில் பணம் செலுத்துங்கள்", inStock: "கையிருப்பில் உள்ளது", outOfStock: "கையிருப்பில் இல்லை",
  },
  "te-IN": {
    shop: "షాప్", dashboard: "డాష్‌బోర్డ్", orders: "ఆర్డర్లు", agent: "నా ఏజెంట్", wallet: "వాలెట్", voiceLab: "వాయిస్ ల్యాబ్",
    heroTitle: "మీకు ఏం కావాలో చెప్పండి.",
    heroSub: "10 భారతీయ భాషల్లో దేనిలోనైనా మాట్లాడండి. Gnani అర్థం చేసుకుంటుంది, మా సహాయకుడు కార్ట్ నింపుతాడు, మీరు ట్యాప్ చేసే వరకు చెల్లింపు జరగదు.",
    tapToSpeak: "మాట్లాడటానికి ట్యాప్ చేయండి", listening: "వింటోంది…", thinking: "ఆలోచిస్తోంది…", speaking: "మాట్లాడుతోంది…", tapToStop: "ఆపడానికి ట్యాప్ చేయండి",
    typeInstead: "టైప్ చేయండి", send: "పంపు", youSaid: "మీరు అన్నది", cart: "కార్ట్", total: "మొత్తం", emptyCart: "మీ కార్ట్ ఖాళీగా ఉంది",
    add: "జోడించు", buyNow: "ఇప్పుడే కొను", payWallet: "వాలెట్‌తో చెల్లించు", payCod: "క్యాష్ ఆన్ డెలివరీ", confirm: "నిర్ధారించు",
    decline: "తిరస్కరించు", needsTap: "మీ ట్యాప్ కావాలి", balance: "బ్యాలెన్స్", demoMoney: "డెమో డబ్బు", search: "ఉత్పత్తులను వెతకండి",
    realtime: "లైవ్ సంభాషణ", pushToTalk: "నొక్కి మాట్లాడు", voice: "వాయిస్", language: "భాష",
    underTheHood: "లోపల ఏం జరిగింది", newChat: "కొత్త సంభాషణ", signOut: "సైన్ అవుట్", orderPlaced: "ఆర్డర్ పూర్తయింది",
    codPlaced: "ఆర్డర్ పూర్తయింది — డెలివరీలో నగదు చెల్లించండి", inStock: "స్టాక్‌లో ఉంది", outOfStock: "స్టాక్ లేదు",
  },
  "kn-IN": {
    shop: "ಅಂಗಡಿ", dashboard: "ಡ್ಯಾಶ್‌ಬೋರ್ಡ್", orders: "ಆರ್ಡರ್‌ಗಳು", agent: "ನನ್ನ ಏಜೆಂಟ್", wallet: "ವಾಲೆಟ್", voiceLab: "ವಾಯ್ಸ್ ಲ್ಯಾಬ್",
    heroTitle: "ನಿಮಗೆ ಏನು ಬೇಕು ಎಂದು ಹೇಳಿ.",
    heroSub: "10 ಭಾರತೀಯ ಭಾಷೆಗಳಲ್ಲಿ ಯಾವುದರಲ್ಲಾದರೂ ಮಾತನಾಡಿ. Gnani ಅರ್ಥಮಾಡಿಕೊಳ್ಳುತ್ತದೆ, ಸಹಾಯಕ ಕಾರ್ಟ್ ತುಂಬುತ್ತಾನೆ, ನೀವು ಟ್ಯಾಪ್ ಮಾಡುವವರೆಗೆ ಪಾವತಿ ಆಗುವುದಿಲ್ಲ.",
    tapToSpeak: "ಮಾತನಾಡಲು ಟ್ಯಾಪ್ ಮಾಡಿ", listening: "ಕೇಳುತ್ತಿದೆ…", thinking: "ಯೋಚಿಸುತ್ತಿದೆ…", speaking: "ಮಾತನಾಡುತ್ತಿದೆ…", tapToStop: "ನಿಲ್ಲಿಸಲು ಟ್ಯಾಪ್ ಮಾಡಿ",
    typeInstead: "ಟೈಪ್ ಮಾಡಿ", send: "ಕಳುಹಿಸಿ", youSaid: "ನೀವು ಹೇಳಿದ್ದು", cart: "ಕಾರ್ಟ್", total: "ಒಟ್ಟು", emptyCart: "ನಿಮ್ಮ ಕಾರ್ಟ್ ಖಾಲಿಯಾಗಿದೆ",
    add: "ಸೇರಿಸಿ", buyNow: "ಈಗ ಖರೀದಿಸಿ", payWallet: "ವಾಲೆಟ್‌ನಿಂದ ಪಾವತಿಸಿ", payCod: "ಕ್ಯಾಶ್ ಆನ್ ಡೆಲಿವರಿ", confirm: "ದೃಢೀಕರಿಸಿ",
    decline: "ನಿರಾಕರಿಸಿ", needsTap: "ನಿಮ್ಮ ಟ್ಯಾಪ್ ಬೇಕು", balance: "ಬ್ಯಾಲೆನ್ಸ್", demoMoney: "ಡೆಮೊ ಹಣ", search: "ಉತ್ಪನ್ನಗಳನ್ನು ಹುಡುಕಿ",
    realtime: "ಲೈವ್ ಸಂಭಾಷಣೆ", pushToTalk: "ಒತ್ತಿ ಮಾತನಾಡಿ", voice: "ಧ್ವನಿ", language: "ಭಾಷೆ",
    underTheHood: "ಒಳಗೆ ಏನಾಯಿತು", newChat: "ಹೊಸ ಸಂಭಾಷಣೆ", signOut: "ಸೈನ್ ಔಟ್", orderPlaced: "ಆರ್ಡರ್ ಆಗಿದೆ",
    codPlaced: "ಆರ್ಡರ್ ಆಗಿದೆ — ಡೆಲಿವರಿಯಲ್ಲಿ ನಗದು ಪಾವತಿಸಿ", inStock: "ಸ್ಟಾಕ್‌ನಲ್ಲಿದೆ", outOfStock: "ಸ್ಟಾಕ್ ಇಲ್ಲ",
  },
  "ml-IN": {
    shop: "കട", dashboard: "ഡാഷ്‌ബോർഡ്", orders: "ഓർഡറുകൾ", agent: "എന്റെ ഏജന്റ്", wallet: "വാലറ്റ്", voiceLab: "വോയ്സ് ലാബ്",
    heroTitle: "എന്താണ് വേണ്ടതെന്ന് പറയൂ.",
    heroSub: "10 ഇന്ത്യൻ ഭാഷകളിൽ ഏതിലും സംസാരിക്കൂ. Gnani മനസ്സിലാക്കുന്നു, സഹായി കാർട്ട് നിറയ്ക്കുന്നു, നിങ്ങൾ ടാപ്പ് ചെയ്യുന്നതുവരെ പണം നൽകില്ല.",
    tapToSpeak: "സംസാരിക്കാൻ ടാപ്പ് ചെയ്യുക", listening: "കേൾക്കുന്നു…", thinking: "ആലോചിക്കുന്നു…", speaking: "സംസാരിക്കുന്നു…", tapToStop: "നിർത്താൻ ടാപ്പ് ചെയ്യുക",
    typeInstead: "ടൈപ്പ് ചെയ്യുക", send: "അയയ്ക്കുക", youSaid: "നിങ്ങൾ പറഞ്ഞത്", cart: "കാർട്ട്", total: "ആകെ", emptyCart: "നിങ്ങളുടെ കാർട്ട് ശൂന്യമാണ്",
    add: "ചേർക്കുക", buyNow: "ഇപ്പോൾ വാങ്ങുക", payWallet: "വാലറ്റിൽ നിന്ന് അടയ്ക്കുക", payCod: "ക്യാഷ് ഓൺ ഡെലിവറി", confirm: "സ്ഥിരീകരിക്കുക",
    decline: "നിരസിക്കുക", needsTap: "നിങ്ങളുടെ ടാപ്പ് വേണം", balance: "ബാലൻസ്", demoMoney: "ഡെമോ പണം", search: "ഉൽപ്പന്നങ്ങൾ തിരയുക",
    realtime: "തത്സമയ സംഭാഷണം", pushToTalk: "അമർത്തി സംസാരിക്കുക", voice: "ശബ്ദം", language: "ഭാഷ",
    underTheHood: "ഉള്ളിൽ എന്ത് നടന്നു", newChat: "പുതിയ സംഭാഷണം", signOut: "സൈൻ ഔട്ട്", orderPlaced: "ഓർഡർ ചെയ്തു",
    codPlaced: "ഓർഡർ ചെയ്തു — ഡെലിവറിയിൽ പണം നൽകുക", inStock: "സ്റ്റോക്കുണ്ട്", outOfStock: "സ്റ്റോക്കില്ല",
  },
  "mr-IN": {
    shop: "दुकान", dashboard: "डॅशबोर्ड", orders: "ऑर्डर", agent: "माझा एजंट", wallet: "वॉलेट", voiceLab: "व्हॉइस लॅब",
    heroTitle: "फक्त सांगा, काय हवे आहे.",
    heroSub: "10 भारतीय भाषांपैकी कोणत्याही भाषेत बोला. Gnani समजते, आमचा सहाय्यक कार्ट भरतो, आणि तुमच्या टॅपशिवाय पैसे दिले जात नाहीत.",
    tapToSpeak: "बोलण्यासाठी टॅप करा", listening: "ऐकत आहे…", thinking: "विचार करत आहे…", speaking: "बोलत आहे…", tapToStop: "थांबवण्यासाठी टॅप करा",
    typeInstead: "टाइप करा", send: "पाठवा", youSaid: "तुम्ही म्हणालात", cart: "कार्ट", total: "एकूण", emptyCart: "तुमचे कार्ट रिकामे आहे",
    add: "जोडा", buyNow: "आता खरेदी करा", payWallet: "वॉलेटने भरा", payCod: "कॅश ऑन डिलिव्हरी", confirm: "पुष्टी करा",
    decline: "नाकारा", needsTap: "तुमचा टॅप हवा", balance: "शिल्लक", demoMoney: "डेमो रक्कम", search: "उत्पादने शोधा",
    realtime: "थेट संवाद", pushToTalk: "दाबून बोला", voice: "आवाज", language: "भाषा",
    underTheHood: "आत काय झाले", newChat: "नवीन संवाद", signOut: "साइन आउट", orderPlaced: "ऑर्डर झाली",
    codPlaced: "ऑर्डर झाली — डिलिव्हरीला रोख द्या", inStock: "स्टॉकमध्ये", outOfStock: "स्टॉक संपला",
  },
  "bn-IN": {
    shop: "দোকান", dashboard: "ড্যাশবোর্ড", orders: "অর্ডার", agent: "আমার এজেন্ট", wallet: "ওয়ালেট", voiceLab: "ভয়েস ল্যাব",
    heroTitle: "শুধু বলুন, কী লাগবে।",
    heroSub: "১০টি ভারতীয় ভাষার যেকোনোটিতে বলুন। Gnani বোঝে, আমাদের সহকারী কার্ট ভরায়, আর আপনার ট্যাপ ছাড়া কোনো পেমেন্ট হয় না।",
    tapToSpeak: "বলতে ট্যাপ করুন", listening: "শুনছে…", thinking: "ভাবছে…", speaking: "বলছে…", tapToStop: "থামাতে ট্যাপ করুন",
    typeInstead: "টাইপ করুন", send: "পাঠান", youSaid: "আপনি বললেন", cart: "কার্ট", total: "মোট", emptyCart: "আপনার কার্ট খালি",
    add: "যোগ করুন", buyNow: "এখনই কিনুন", payWallet: "ওয়ালেটে পেমেন্ট", payCod: "ক্যাশ অন ডেলিভারি", confirm: "নিশ্চিত করুন",
    decline: "বাতিল করুন", needsTap: "আপনার ট্যাপ লাগবে", balance: "ব্যালেন্স", demoMoney: "ডেমো টাকা", search: "পণ্য খুঁজুন",
    realtime: "লাইভ কথোপকথন", pushToTalk: "চেপে বলুন", voice: "কণ্ঠ", language: "ভাষা",
    underTheHood: "ভেতরে কী হলো", newChat: "নতুন কথোপকথন", signOut: "সাইন আউট", orderPlaced: "অর্ডার হয়েছে",
    codPlaced: "অর্ডার হয়েছে — ডেলিভারিতে নগদ দিন", inStock: "স্টকে আছে", outOfStock: "স্টক নেই",
  },
  "gu-IN": {
    shop: "દુકાન", dashboard: "ડેશબોર્ડ", orders: "ઓર્ડર", agent: "મારો એજન્ટ", wallet: "વૉલેટ", voiceLab: "વૉઇસ લેબ",
    heroTitle: "બસ બોલો, શું જોઈએ છે.",
    heroSub: "10 ભારતીય ભાષાઓમાંથી કોઈપણમાં બોલો. Gnani સમજે છે, અમારો સહાયક કાર્ટ ભરે છે, અને તમારા ટેપ વગર ચુકવણી થતી નથી.",
    tapToSpeak: "બોલવા માટે ટેપ કરો", listening: "સાંભળી રહ્યું છે…", thinking: "વિચારી રહ્યું છે…", speaking: "બોલી રહ્યું છે…", tapToStop: "રોકવા માટે ટેપ કરો",
    typeInstead: "ટાઇપ કરો", send: "મોકલો", youSaid: "તમે કહ્યું", cart: "કાર્ટ", total: "કુલ", emptyCart: "તમારું કાર્ટ ખાલી છે",
    add: "ઉમેરો", buyNow: "હમણાં ખરીદો", payWallet: "વૉલેટથી ચૂકવો", payCod: "કેશ ઓન ડિલિવરી", confirm: "પુષ્ટિ કરો",
    decline: "નકારો", needsTap: "તમારો ટેપ જોઈએ", balance: "બેલેન્સ", demoMoney: "ડેમો રકમ", search: "ઉત્પાદનો શોધો",
    realtime: "લાઇવ વાતચીત", pushToTalk: "દબાવીને બોલો", voice: "અવાજ", language: "ભાષા",
    underTheHood: "અંદર શું થયું", newChat: "નવી વાતચીત", signOut: "સાઇન આઉટ", orderPlaced: "ઓર્ડર થઈ ગયો",
    codPlaced: "ઓર્ડર થઈ ગયો — ડિલિવરી પર રોકડા આપો", inStock: "સ્ટોકમાં છે", outOfStock: "સ્ટોક નથી",
  },
  "pa-IN": {
    shop: "ਦੁਕਾਨ", dashboard: "ਡੈਸ਼ਬੋਰਡ", orders: "ਆਰਡਰ", agent: "ਮੇਰਾ ਏਜੰਟ", wallet: "ਵਾਲਿਟ", voiceLab: "ਵੌਇਸ ਲੈਬ",
    heroTitle: "ਬੱਸ ਬੋਲੋ, ਕੀ ਚਾਹੀਦਾ ਹੈ।",
    heroSub: "10 ਭਾਰਤੀ ਭਾਸ਼ਾਵਾਂ ਵਿੱਚੋਂ ਕਿਸੇ ਵਿੱਚ ਵੀ ਬੋਲੋ। Gnani ਸਮਝਦਾ ਹੈ, ਸਾਡਾ ਸਹਾਇਕ ਕਾਰਟ ਭਰਦਾ ਹੈ, ਅਤੇ ਤੁਹਾਡੇ ਟੈਪ ਤੋਂ ਬਿਨਾਂ ਕੋਈ ਭੁਗਤਾਨ ਨਹੀਂ ਹੁੰਦਾ।",
    tapToSpeak: "ਬੋਲਣ ਲਈ ਟੈਪ ਕਰੋ", listening: "ਸੁਣ ਰਿਹਾ ਹੈ…", thinking: "ਸੋਚ ਰਿਹਾ ਹੈ…", speaking: "ਬੋਲ ਰਿਹਾ ਹੈ…", tapToStop: "ਰੋਕਣ ਲਈ ਟੈਪ ਕਰੋ",
    typeInstead: "ਟਾਈਪ ਕਰੋ", send: "ਭੇਜੋ", youSaid: "ਤੁਸੀਂ ਕਿਹਾ", cart: "ਕਾਰਟ", total: "ਕੁੱਲ", emptyCart: "ਤੁਹਾਡਾ ਕਾਰਟ ਖਾਲੀ ਹੈ",
    add: "ਜੋੜੋ", buyNow: "ਹੁਣੇ ਖਰੀਦੋ", payWallet: "ਵਾਲਿਟ ਨਾਲ ਭੁਗਤਾਨ", payCod: "ਕੈਸ਼ ਆਨ ਡਿਲਿਵਰੀ", confirm: "ਪੁਸ਼ਟੀ ਕਰੋ",
    decline: "ਰੱਦ ਕਰੋ", needsTap: "ਤੁਹਾਡਾ ਟੈਪ ਚਾਹੀਦਾ", balance: "ਬਕਾਇਆ", demoMoney: "ਡੈਮੋ ਰਕਮ", search: "ਉਤਪਾਦ ਲੱਭੋ",
    realtime: "ਲਾਈਵ ਗੱਲਬਾਤ", pushToTalk: "ਦਬਾ ਕੇ ਬੋਲੋ", voice: "ਆਵਾਜ਼", language: "ਭਾਸ਼ਾ",
    underTheHood: "ਅੰਦਰ ਕੀ ਹੋਇਆ", newChat: "ਨਵੀਂ ਗੱਲਬਾਤ", signOut: "ਸਾਈਨ ਆਊਟ", orderPlaced: "ਆਰਡਰ ਹੋ ਗਿਆ",
    codPlaced: "ਆਰਡਰ ਹੋ ਗਿਆ — ਡਿਲਿਵਰੀ 'ਤੇ ਨਕਦ ਦਿਓ", inStock: "ਸਟਾਕ ਵਿੱਚ", outOfStock: "ਸਟਾਕ ਖਤਮ",
  },
};

const STORAGE_KEY = "gnani-shop-lang";

interface LangCtx {
  lang: LangCode;
  setLang: (code: string) => void;
  t: (key: Key) => string;
}

const Ctx = createContext<LangCtx>({ lang: "en-IN", setLang: () => {}, t: (k) => T["en-IN"][k] });

function isLang(code: string | null | undefined): code is LangCode {
  return !!code && code in T;
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<LangCode>("en-IN");

  useEffect(() => {
    // Deferred so the restore doesn't run synchronously inside the effect body.
    Promise.resolve().then(() => {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (isLang(saved)) setLangState(saved);
      } catch {
        // storage unavailable — English
      }
    });
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang.slice(0, 2);
  }, [lang]);

  const setLang = useCallback((code: string) => {
    if (!isLang(code)) return;
    setLangState(code);
    try {
      window.localStorage.setItem(STORAGE_KEY, code);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo<LangCtx>(() => ({ lang, setLang, t: (k: Key) => T[lang][k] ?? T["en-IN"][k] }), [lang, setLang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): LangCtx {
  return useContext(Ctx);
}

export function nativeName(code: string | null | undefined): string {
  return LANGUAGES.find((l) => l.code === code)?.native ?? code ?? "";
}
