
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
from datetime import datetime
import os
from dotenv import load_dotenv

# Last inn miljøvariabler fra .env-fil
load_dotenv()

# Sidekonfigurasjon
st.set_page_config(
    page_title="Sladrehank - Innsikt i Arbeidsledighet fra SSB",
    page_icon="📊",
    layout="wide"
)

# Hovedtittel og beskrivelse
st.title("🇳🇴 Trender i Arbeidsledighet i Norge (2015-2024)")
st.markdown("""
Denne applikasjonen visualiserer arbeidsledighetsdata fra Statistisk sentralbyrå (SSB)
og gir innsikt i arbeidsledighetstrender på tvers av ulike demografiske grupper.
Datakilde: [SSB Tabell 08517](https://www.ssb.no/statbank/table/08517/)
""")

# Funksjon for å hente data fra SSB API
@st.cache_data(ttl=3600) # Cache data i 1 time
def fetch_ssb_data():
    """
    Henter arbeidsledighetsdata fra SSB API (tabell 08517)
    Returnerer en prosessert DataFrame eller None ved feil.
    """
    url = "https://data.ssb.no/api/v0/no/table/08517/"

    payload = {
        "query": [
            {"code": "Kjonn", "selection": {"filter": "item", "values": ["0", "1", "2"]}},  # 0=Begge kjønn, 1=Menn, 2=Kvinner
            {"code": "Alder", "selection": {"filter": "item", "values": ["15-74", "15-24", "25-54", "55-74"]}},  # Kjerne aldersgrupper
            {"code": "ContentsCode", "selection": {"filter": "item", "values": ["Personer"]}},  # Antall personer
            {"code": "Tid", "selection": {"filter": "item", "values": ["2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024"]}}
        ],
        "response": {"format": "json-stat2"}
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Gir unntak for 4XX/5XX-responser
        data = response.json()

        # Trekk ut relevante data
        dimensions = data["dimension"]
        values = data["value"]

        # Lag tomme lister for DataFrame
        records = []

        # Map koder til lesbare etiketter (Bruker norsk her)
        gender_map = {"0": "Begge kjønn", "1": "Menn", "2": "Kvinner"}

        # Hent etiketter og indekser for dimensjoner
        # Sjekk om 'label' eksisterer, ellers bruk 'index'
        time_labels = dimensions["Tid"]["category"]["label"] if "label" in dimensions["Tid"]["category"] else dimensions["Tid"]["category"]["index"]
        gender_labels = dimensions["Kjonn"]["category"]["label"] if "label" in dimensions["Kjonn"]["category"] else dimensions["Kjonn"]["category"]["index"]
        age_labels = dimensions["Alder"]["category"]["label"] if "label" in dimensions["Alder"]["category"] else dimensions["Alder"]["category"]["index"]

        time_indices = list(dimensions["Tid"]["category"]["index"].keys())
        gender_indices = list(dimensions["Kjonn"]["category"]["index"].keys())
        age_indices = list(dimensions["Alder"]["category"]["index"].keys())

        # Gå gjennom dimensjoner for å lage DataFrame-rader
        for time_idx, year_code in enumerate(time_indices):
            year_label = time_labels.get(year_code, year_code) # Bruk label hvis den finnes
            for gender_idx, gender_code in enumerate(gender_indices):
                gender_label = gender_map.get(gender_code, gender_code) # Bruk vår norske mapping
                for age_idx, age_code in enumerate(age_indices):
                    age_label = age_labels.get(age_code, age_code) # Bruk label hvis den finnes
                    # Beregn posisjonen i den flate verdi-arrayen
                    # Posisjonsberegningen må matche rekkefølgen SSB returnerer data i (Tid, Kjonn, Alder)
                    pos = (time_idx * len(gender_indices) * len(age_indices)) + \
                          (gender_idx * len(age_indices)) + \
                          age_idx

                    # Hent verdien på denne posisjonen
                    value = values[pos] if pos < len(values) else None

                    # Lag en rad
                    records.append({
                        "År": year_label,
                        "Kjønn": gender_label,
                        "Aldersgruppe": age_label,
                        "Antall Arbeidsledige": value
                    })

        # Lag DataFrame
        df = pd.DataFrame(records)

        # Konverter datatyper
        df["År"] = df["År"].astype(int)
        df["Antall Arbeidsledige"] = pd.to_numeric(df["Antall Arbeidsledige"], errors="coerce") # 'coerce' setter ugyldige verdier til NaN

        return df

    except Exception as e:
        st.error(f"Feil ved henting av data fra SSB: {str(e)}")
        return None

# Funksjon for å få KI-innsikt ved hjelp av Google Gemini
def get_ai_insight(data, prompt_context):
    """
    Genererer KI-innsikt ved hjelp av Google Gemini API basert på gitte data og kontekst.
    """
    try:
        # Sjekk om API-nøkkel er tilgjengelig
        if not st.session_state.get("GEMINI_API_KEY"):
            return "Vennligst oppgi en Google Gemini API-nøkkel for å generere innsikt."

        # Konfigurer Gemini API
        genai.configure(api_key=st.session_state["GEMINI_API_KEY"])

        # Bruk en spesifikk modell
        model = genai.GenerativeModel('gemini-1.5-flash') # Eller annen passende modell

        # Generer respons
        full_prompt = prompt_context + "\n\nData:\n" + data.to_string(index=False) # index=False for renere data-input
        response = model.generate_content(full_prompt)

        return response.text
    except Exception as e:
        # Gi mer spesifikk feilmelding hvis mulig
        error_message = f"Kunne ikke generere KI-innsikt: {str(e)}"
        if "API key not valid" in str(e):
             error_message += "\nVennligst sjekk om API-nøkkelen er korrekt."
        return error_message


# Sidefelt for innstillinger
st.sidebar.title("⚙️ Innstillinger")

# Last API-nøkkel fra miljøvariabel
api_key_from_env = os.getenv("GEMINI_API_KEY")

# Sett API-nøkkel i session state hvis tilgjengelig fra miljøet
if api_key_from_env:
    st.session_state["GEMINI_API_KEY"] = api_key_from_env
    st.sidebar.success("✅ API-nøkkel lastet fra .env-fil")
else:
    # Bruk inputfelt hvis nøkkel ikke finnes i .env
    api_key_input = st.sidebar.text_input("Skriv inn Google Gemini API-nøkkel", type="password", key="api_key_input_sidebar")
    if api_key_input:
        st.session_state["GEMINI_API_KEY"] = api_key_input
        st.sidebar.success("✅ API-nøkkel mottatt")
    else:
        st.sidebar.warning("⚠️ Ingen API-nøkkel funnet i .env-fil eller oppgitt. KI-innsikt vil ikke være tilgjengelig.")

# Applikasjonsinformasjon
st.sidebar.title("📊 Om Denne Appen")
st.sidebar.markdown("""
Denne applikasjonen visualiserer arbeidsledighetsdata fra Statistisk sentralbyrå (SSB) for perioden 2015 til 2024.

### Funksjoner:
- Analyse av generell arbeidsledighetstrend
- Kjønnsbasert sammenligning
- Analyse av aldersgrupper på tvers av demografi
- KI-drevet innsikt levert av Google Gemini

### Datakilde:
Dataene er hentet fra [SSB Tabell 08517](https://www.ssb.no/statbank/table/08517/) via API.

### Slik Bruker Du Appen:
Utforsk de ulike grafene og visualiseringene på hovedsiden. Hver seksjon inkluderer KI-generert innsikt som fremhever nøkkeltrender og mønstre i dataene (krever API-nøkkel).
""")

# Footer i sidefeltet
st.sidebar.markdown("---")
st.sidebar.caption("© 2025 Sladrehank - Innsikt i Norsk Arbeidsledighet")

# Last data
with st.spinner("Henter arbeidsledighetsdata fra SSB..."):
    df = fetch_ssb_data()

if df is not None and not df.empty: # Sjekk også om DataFrame ikke er tom
    # Vis dataoversikt
    st.subheader("Dataoversikt")
    with st.expander("Vis Rådata"):
        st.dataframe(df)

    # Hovedrad for generell trend
    st.subheader("Generell Arbeidsledighetstrend (2015-2024)")

    # Filtrer data for generell trend
    # Bruk norske etiketter som definert i fetch_ssb_data
    overall_df = df[(df["Kjønn"] == "Begge kjønn") & (df["Aldersgruppe"] == "15-74 år")] # SSB bruker "15-74 år"

    if not overall_df.empty:
        # Lag linjediagram
        fig_overall = px.line(
            overall_df,
            x="År",
            y="Antall Arbeidsledige",
            markers=True,
            title="Total Arbeidsledighet i Norge (Alder 15-74 år)",
            labels={"Antall Arbeidsledige": "Antall Arbeidsledige", "År": "År"} # Bruk norske aksetitler
        )
        fig_overall.update_layout(
            xaxis=dict(tickmode='linear', dtick=1), # Sørger for at alle år vises
            hovermode="x unified" # Bedre hover-opplevelse
        )

        col1, col2 = st.columns([2, 1]) # Gi grafen mer plass

        with col1:
            st.plotly_chart(fig_overall, use_container_width=True)

        with col2:
            st.markdown("### KI-innsikt")
            if st.session_state.get("GEMINI_API_KEY"):
                # Norsk prompt for generell trend
                overall_prompt = """
                Analyser følgende data som viser total arbeidsledighet i Norge (alder 15-74 år) fra 2015 til 2024.
                Oppsummer hovedtrenden i 2-3 setninger. Nevn den overordnede retningen (økning/nedgang/stabilt) og eventuelle signifikante topper eller bunnpunkter i perioden.
                Hold svaret kortfattet og rettet mot et generelt publikum. Svar på norsk.
                """
                with st.spinner("Genererer innsikt..."):
                    overall_insight = get_ai_insight(overall_df[["År", "Antall Arbeidsledige"]], overall_prompt) # Send kun relevant data
                    st.markdown(overall_insight)
                    st.caption("KI-generert oppsummering basert på SSB-data")
            else:
                st.info("Skriv inn en Google Gemini API-nøkkel i sidefeltet for å generere KI-innsikt")
    else:
        st.warning("Ingen data funnet for den generelle trenden (Begge kjønn, 15-74 år).")


    # Kjønnssammenligning
    st.subheader("Kjønnssammenligning (2015-2024)")

    # Filtrer data for kjønn (Menn/Kvinner) for aldersgruppen 15-74 år
    gender_df = df[(df["Kjønn"].isin(["Menn", "Kvinner"])) & (df["Aldersgruppe"] == "15-74 år")]

    if not gender_df.empty:
        fig_gender = px.line(
            gender_df,
            x="År",
            y="Antall Arbeidsledige",
            color="Kjønn", # Fargelegg linjene basert på kjønn
            markers=True,
            title="Arbeidsledighet etter Kjønn (Alder 15-74 år)",
            labels={"Antall Arbeidsledige": "Antall Arbeidsledige", "År": "År", "Kjønn": "Kjønn"} # Norske etiketter
        )
        fig_gender.update_layout(
            xaxis=dict(tickmode='linear', dtick=1),
            hovermode="x unified"
        )

        col1_gender, col2_gender = st.columns([2, 1])

        with col1_gender:
            st.plotly_chart(fig_gender, use_container_width=True)

        with col2_gender:
            st.markdown("### KI-innsikt")
            if st.session_state.get("GEMINI_API_KEY"):
                # Norsk prompt for kjønnsforskjeller
                gender_prompt = """
                Analyser arbeidsledighetstallene for menn og kvinner (alder 15-74 år) i Norge fra 2015 til 2024 basert på dataene nedenfor.
                Oppsummer de viktigste forskjellene i trender mellom kjønnene i 2-3 setninger.
                Var ledigheten generelt høyere for menn eller kvinner? Endret gapet seg merkbart over tid?
                Hold svaret kortfattet og rettet mot et generelt publikum. Svar på norsk.
                """
                with st.spinner("Genererer innsikt..."):
                    # Send kun relevant data og unngå duplikater hvis mulig
                    gender_insight_data = gender_df[["År", "Kjønn", "Antall Arbeidsledige"]].drop_duplicates()
                    gender_insight = get_ai_insight(gender_insight_data, gender_prompt)
                    st.markdown(gender_insight)
                    st.caption("KI-generert oppsummering basert på SSB-data")
            else:
                st.info("Skriv inn en Google Gemini API-nøkkel i sidefeltet for å generere KI-innsikt")
    else:
        st.warning("Ingen data funnet for kjønnssammenligning (Menn/Kvinner, 15-74 år).")


    # Aldersgruppetrender (Totalt)
    st.subheader("Aldersgruppesammenligning (2015-2024)")

    # Filtrer for totalt (Begge kjønn) og de ulike aldersgruppene (unntatt 15-74 totalt)
    age_df = df[(df["Kjønn"] == "Begge kjønn") & (df["Aldersgruppe"].isin(["15-24 år", "25-54 år", "55-74 år"]))]

    if not age_df.empty:
        fig_age = px.line(
            age_df,
            x="År",
            y="Antall Arbeidsledige",
            color="Aldersgruppe", # Fargelegg etter aldersgruppe
            markers=True,
            title="Arbeidsledighet etter Aldersgruppe (Begge Kjønn)",
            labels={"Antall Arbeidsledige": "Antall Arbeidsledige", "År": "År", "Aldersgruppe": "Aldersgruppe"}
        )
        fig_age.update_layout(
            xaxis=dict(tickmode='linear', dtick=1),
            hovermode="x unified"
        )

        col1_age, col2_age = st.columns([2, 1])

        with col1_age:
            st.plotly_chart(fig_age, use_container_width=True)

        with col2_age:
            st.markdown("### KI-innsikt")
            if st.session_state.get("GEMINI_API_KEY"):
                # Norsk prompt for aldersgrupper
                age_prompt = """
                Analyser arbeidsledighetsdataene for ulike aldersgrupper (15-24 år, 25-54 år, 55-74 år) for begge kjønn samlet i Norge fra 2015 til 2024.
                Oppsummer i 3-4 setninger: Hvilke aldersgrupper hadde generelt høyest og lavest arbeidsledighet?
                Hvilke grupper så de største relative endringene (f.eks. i prosent eller absolutte tall) i perioden?
                Er det noen spesielt markante mønstre eller topper/bunner for enkelte grupper?
                Hold svaret kortfattet og rettet mot et generelt publikum. Svar på norsk.
                """
                with st.spinner("Genererer innsikt..."):
                    age_insight_data = age_df[["År", "Aldersgruppe", "Antall Arbeidsledige"]].drop_duplicates()
                    age_insight = get_ai_insight(age_insight_data, age_prompt)
                    st.markdown(age_insight)
                    st.caption("KI-generert oppsummering basert på SSB-data")
            else:
                st.info("Skriv inn en Google Gemini API-nøkkel i sidefeltet for å generere KI-innsikt")
    else:
        st.warning("Ingen data funnet for aldersgruppesammenligning (Begge kjønn, ulike aldersgrupper).")


    # Aldersgrupper etter kjønn
    st.subheader("Aldersgruppetrender etter Kjønn")

    # Bruk norske etiketter for faner
    tab1, tab2 = st.tabs(["Menn", "Kvinner"])

    with tab1:
        # Filtrer for menn og relevante aldersgrupper
        male_age_df = df[(df["Kjønn"] == "Menn") & (df["Aldersgruppe"].isin(["15-24 år", "25-54 år", "55-74 år"]))]

        if not male_age_df.empty:
            fig_male_age = px.line(
                male_age_df,
                x="År",
                y="Antall Arbeidsledige",
                color="Aldersgruppe",
                markers=True,
                title="Arbeidsledighet Blant Menn etter Aldersgruppe",
                labels={"Antall Arbeidsledige": "Antall Arbeidsledige", "År": "År", "Aldersgruppe": "Aldersgruppe"}
            )
            fig_male_age.update_layout(
                xaxis=dict(tickmode='linear', dtick=1),
                hovermode="x unified"
            )

            col1_male_age, col2_male_age = st.columns([2, 1])

            with col1_male_age:
                st.plotly_chart(fig_male_age, use_container_width=True)

            with col2_male_age:
                st.markdown("### KI-innsikt")
                if st.session_state.get("GEMINI_API_KEY"):
                    # Norsk prompt for menn fordelt på alder
                    male_age_prompt = """
                    Analyser arbeidsledighetsdataene for ulike aldersgrupper (15-24 år, 25-54 år, 55-74 år) spesifikt for menn i Norge fra 2015 til 2024.
                    Oppsummer i 2-3 setninger: Hvilke aldersgrupper hadde høyest og lavest arbeidsledighet blant menn?
                    Identifiser eventuelle signifikante trender eller endringer for menn i disse gruppene i perioden.
                    Hold svaret kortfattet og rettet mot et generelt publikum. Svar på norsk.
                    """
                    with st.spinner("Genererer innsikt..."):
                        male_age_insight_data = male_age_df[["År", "Aldersgruppe", "Antall Arbeidsledige"]].drop_duplicates()
                        male_age_insight = get_ai_insight(male_age_insight_data, male_age_prompt)
                        st.markdown(male_age_insight)
                        st.caption("KI-generert oppsummering basert på SSB-data")
                else:
                    st.info("Skriv inn en Google Gemini API-nøkkel i sidefeltet for å generere KI-innsikt")
        else:
            st.warning("Ingen data funnet for menn fordelt på aldersgrupper.")


    with tab2:
         # Filtrer for kvinner og relevante aldersgrupper
        female_age_df = df[(df["Kjønn"] == "Kvinner") & (df["Aldersgruppe"].isin(["15-24 år", "25-54 år", "55-74 år"]))]

        if not female_age_df.empty:
            fig_female_age = px.line(
                female_age_df,
                x="År",
                y="Antall Arbeidsledige",
                color="Aldersgruppe",
                markers=True,
                title="Arbeidsledighet Blant Kvinner etter Aldersgruppe",
                labels={"Antall Arbeidsledige": "Antall Arbeidsledige", "År": "År", "Aldersgruppe": "Aldersgruppe"}
            )
            fig_female_age.update_layout(
                xaxis=dict(tickmode='linear', dtick=1),
                hovermode="x unified"
            )

            col1_female_age, col2_female_age = st.columns([2, 1])

            with col1_female_age:
                st.plotly_chart(fig_female_age, use_container_width=True)

            with col2_female_age:
                st.markdown("### KI-innsikt")
                if st.session_state.get("GEMINI_API_KEY"):
                     # Norsk prompt for kvinner fordelt på alder
                    female_age_prompt = """
                    Analyser arbeidsledighetsdataene for ulike aldersgrupper (15-24 år, 25-54 år, 55-74 år) spesifikt for kvinner i Norge fra 2015 til 2024.
                    Oppsummer i 2-3 setninger: Hvilke aldersgrupper hadde høyest og lavest arbeidsledighet blant kvinner?
                    Identifiser eventuelle signifikante trender eller endringer for kvinner i disse gruppene i perioden.
                    Hold svaret kortfattet og rettet mot et generelt publikum. Svar på norsk.
                    """
                    with st.spinner("Genererer innsikt..."):
                        female_age_insight_data = female_age_df[["År", "Aldersgruppe", "Antall Arbeidsledige"]].drop_duplicates()
                        female_age_insight = get_ai_insight(female_age_insight_data, female_age_prompt)
                        st.markdown(female_age_insight)
                        st.caption("KI-generert oppsummering basert på SSB-data")
                else:
                    st.info("Skriv inn en Google Gemini API-nøkkel i sidefeltet for å generere KI-innsikt")
        else:
             st.warning("Ingen data funnet for kvinner fordelt på aldersgrupper.")


    # Footer
    st.markdown("---")
    st.caption(f"Sladrehank SSB Innsiktsfunksjon for Arbeidsledighet • Data sist hentet: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
else:
    st.error("Kunne ikke laste eller behandle data. Vennligst sjekk feilmeldingen over eller prøv igjen senere.")