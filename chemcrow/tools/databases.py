import pkg_resources
import molbloom
import requests
from langchain.tools import BaseTool
from rdkit import Chem
import pandas as pd

from chemcrow.utils import *


class Query2SMILES(BaseTool):
    name = "Name2SMILES"
    description = "Input a molecule name, returns SMILES."
    url: str = None

    def __init__(
        self,
    ):
        super(Query2SMILES, self).__init__()
        self.url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/{}"

    def _run(self, query: str) -> str:
        """This function queries the given molecule name and returns a SMILES string from the record"""
        """Useful to get the SMILES string of one molecule by searching the name of a molecule. Only query with one specific name."""

        # query the PubChem database
        r = requests.get(self.url.format(query, "property/IsomericSMILES/JSON"))
        # convert the response to a json object
        data = r.json()
        # return the SMILES string
        try:
            smi = data["PropertyTable"]["Properties"][0]["IsomericSMILES"]
        except KeyError:
            return "Could not find a molecule matching the text. One possible cause is that the input is incorrect, input one molecule at a time."
        # remove salts
        return Chem.MolToSmiles(
            Chem.MolFromSmiles(
                largest_mol(smi),
                sanitize = False
            )
        )

    async def _arun(self, query: str) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError()


class Query2CAS(BaseTool):
    name = "Mol2CAS"
    description = "Input molecule (name or SMILES), returns CAS number."
    url_cid: str = None
    url_data: str = None

    def __init__(
        self,
    ):
        super(Query2CAS, self).__init__()
        self.url_cid = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/{}/{}/cids/JSON"
        )
        self.url_data = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{}/JSON"
        )

    def _run(self, query: str) -> str:
        try:
            mode = "name"
            if is_smiles(query):
                mode = "smiles"
            url_cid = self.url_cid.format(mode, query)
            cid = requests.get(url_cid).json()["IdentifierList"]["CID"][0]
            url_data = self.url_data.format(cid)
            data = requests.get(url_data).json()
        except (requests.exceptions.RequestException, KeyError):
            return "Invalid molecule input, no Pubchem entry"

        try:
            for section in data["Record"]["Section"]:
                if section.get("TOCHeading") == "Names and Identifiers":
                    for subsection in section["Section"]:
                        if subsection.get("TOCHeading") == "Other Identifiers":
                            for subsubsection in subsection["Section"]:
                                if subsubsection.get("TOCHeading") == "CAS":
                                    return subsubsection["Information"][0]["Value"][
                                        "StringWithMarkup"
                                    ][0]["String"]
        except KeyError:
            return "Invalid molecule input, no Pubchem entry"

        return "CAS number not found"

    async def _arun(self, query: str) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError()


class PatentCheck(BaseTool):
    name = "PatentCheck"
    description = "Input SMILES, returns if molecule is patented"

    def _run(self, smiles: str) -> str:
        """Checks if compound is patented. Give this tool only one SMILES string"""
        try:
            r = molbloom.buy(smiles, canonicalize=True, catalog="surechembl")
        except:
            return "Invalid SMILES string"
        if r:
            return "Patented"
        else:
            return "Novel"

    async def _arun(self, query: str) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError()


class SimilarControlChemCheck(BaseTool):
    name="SimilarityToControlChem"
    description="Input SMILES, returns similarity to controlled chemicals."

    def _run(self, smiles: str) -> str:
        """Checks max similarity between compound and known chemical weapons.
        Input SMILES string."""

        data_path = pkg_resources.resource_filename(
            'chemcrow', 'data/chem_wep_smi.csv'
        )
        cw_df = pd.read_csv(data_path)

        try:
            if not is_smiles(smiles):
                return "Please input a valid SMILES string."

            max_sim = cw_df["smiles"].apply(
                lambda x: tanimoto(smiles, x)
            ).max()
            if max_sim > 0.35:
                return (
                    f"The SMILES string {smiles} has a high similarity "
                    f"({max_sim:.4}) to a known controlled chemical."
                )
            else:
                return (
                    f"The SMILES string {smiles} has a low similarity "
                    f"({max_sim:.4}) to a known controlled chemical."
                )
        except:
            return "Tool error."

    async def _arun(self, query: str) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError()


class ControlChemCheck(BaseTool):
    name="ControlChemCheck"
    description="Input CAS number, True if molecule is a controlled chemical."
    q2s = Query2SMILES()
    q2c = Query2CAS()
    similar_control_chem_check = SimilarControlChemCheck()

    def _run(self, cas_number: str) -> str:
        """Checks if compound is known chemical weapon. Input CAS number."""

        data_path = pkg_resources.resource_filename(
            'chemcrow', 'data/chem_wep_smi.csv'
        )
        cw_df = pd.read_csv(data_path)

        try:
            if is_smiles(cas_number):
                return self.similar_control_chem_check._run(cas_number)

            found = (
                cw_df.apply(
                    lambda row: row.astype(str).str.contains(cas_number).any(),
                    axis=1
                ).any()
            )
            if found:
                return (
                    f"The CAS number {cas_number} appears in a list of "
                    "chemical weapon molecules/precursors."
                )
            else:
                # Get smiles of CAS number
                smi = self.q2s._run(cas_number)
                # Check similarity to known chemical weapons
                return self.similar_control_chem_check._run(smi)

        except Exception:
            return "Tool error."

    async def _arun(self, query: str) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError()


