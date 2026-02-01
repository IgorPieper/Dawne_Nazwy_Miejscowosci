# Dawne Nazwy Miejscowości

🌍 Strona projektu: https://igorpieper.github.io/Dawne_Nazwy_Miejscowosci/

**Dawne Nazwy Miejscowości** to otwarty, prosty w użyciu projekt, którego celem jest ułatwienie identyfikacji miejscowości występujących w dawnych dokumentach, aktach archiwalnych i źródłach historycznych.

Projekt powstał z bardzo praktycznej potrzeby.
Podczas pracy z **archiwaliami, starymi aktami, księgami metrykalnymi, mapami czy dokumentami urzędowymi** regularnie pojawiają się **dawne, obcojęzyczne lub już nieużywane nazwy miejscowości**. Ich poprawne powiązanie z dzisiejszą lokalizacją bywa trudne, czasochłonne i podatne na błędy — zwłaszcza gdy ta sama nazwa występowała w wielu regionach.

Ten projekt ma to uprościć.

---

## 🎯 Cel projektu

* umożliwić **szybkie wyszukiwanie dawnych nazw miejscowości**
* powiązać je z **obecną nazwą i lokalizacją administracyjną**
* ograniczyć pomyłki wynikające z powtarzających się nazw
* stworzyć **otwartą bazę**, którą można łatwo rozwijać i poprawiać

Projekt jest skierowany m.in. do:

* archiwistów i genealogów
* historyków i regionalistów
* badaczy dawnych dokumentów
* osób pracujących z aktami parafialnymi i urzędowymi
* wszystkich, którzy „kopią w papierach” i trafiają na nazwy, których nie ma już na współczesnych mapach

---

## 🗂 Struktura danych

Dane przechowywane są w jednym, czytelnym pliku:

```
Miejscowosci.json
```

Format jest celowo **prosty i jednoznaczny**:

```json
{
  "miejscowosci": [
    {
      "nazwa": "Wrocław",
      "lokalizacja": "woj. dolnośląskie, pow. m. Wrocław",
      "inne_nazwy": ["Breslau", "Vratislavia"]
    }
  ]
}
```

* `nazwa` – obecna, oficjalna nazwa miejscowości
* `lokalizacja` – opis administracyjny pozwalający jednoznacznie ją zidentyfikować
* `inne_nazwy` – dawne, historyczne lub obcojęzyczne nazwy

---

## 🔍 Wyszukiwarka

Repozytorium zawiera prostą stronę WWW działającą **w 100% w przeglądarce** (bez serwera), która pozwala:

* wyszukiwać po nazwie obecnej
* wyszukiwać po nazwach dawnych / obcych
* filtrować po lokalizacji
* szybko skopiować wyniki

Strona została zaprojektowana tak, aby była **czytelna również dla osób nietechnicznych**.

---

## 🤝 Wkład i rozwój

Projekt jest **otwarty**.

Możesz:

* dodawać nowe miejscowości
* uzupełniać brakujące dawne nazwy
* poprawiać lokalizacje
* zgłaszać błędy lub wątpliwości

Jeśli korzystasz z danych w swojej pracy lub publikacjach, pamiętaj o **podaniu źródła**.

---

## 📜 Licencja

Projekt udostępniony na licencji **MIT License**.

Oznacza to, że:

* możesz korzystać z danych i kodu w dowolnym celu
* możesz je modyfikować i rozpowszechniać
* wymagane jest jedynie zachowanie informacji o autorze i źródle


— to repozytorium jest właśnie dla Ciebie.
