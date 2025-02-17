import os
import warnings
import yaml
from datetime import datetime
from github import Github
from . import implementations
from . import settings
from .families import keys_and_names, arnold_logg_reference, cockburn_fu_reference
from .implementations import VariantNotImplemented
from .markup import insert_links
from .polyset import make_poly_set, make_extra_info


def make_dof_data(ndofs):
    if isinstance(ndofs, list):
        return "<br /><br />".join([f"\\({i}\\):<br />{make_dof_data(j)}"
                                    for a in ndofs for i, j in a.items()])

    dof_text = []
    for i, j in ndofs.items():
        txt = f"{i}: "
        txt += make_formula(j)
        dof_text.append(txt)

    return "<br />".join(dof_text)


def make_formula(data):
    txt = ""
    if "formula" not in data and "oeis" not in data:
        return ", ".join(f"{make_formula(j)} ({i})"
                         for i, j in data.items())
    if "formula" in data:
        txt += "\\("
        if isinstance(data["formula"], list):
            txt += "\\begin{cases}"
            txt += "\\\\".join([f"{c}&{b}" for a in data["formula"] for b, c in a.items()])
            txt += "\\end{cases}"
        else:
            txt += f"{data['formula']}"
        txt += "\\)"
    if "oeis" in data:
        if "formula" in data:
            txt += " ("
        txt += f"<a href='http://oeis.org/{data['oeis']}'>{data['oeis']}</a>"
        if "formula" in data:
            txt += ")"
    return txt


class Categoriser:
    def __init__(self):
        self.elements = []
        self.families = {}
        self.references = {}
        self.categories = {}
        self.implementations = {}

    def recently_added(self, n):
        if self.elements[0].created is None:
            return self.elements[:n]
        return sorted(self.elements, key=lambda e: e.created)[:-n-1:-1]

    def recently_updated(self, n):
        if self.elements[0].modified is None:
            return self.elements[:n]
        return sorted(self.elements, key=lambda e: e.modified)[:-n-1:-1]

    def load_categories(self, file):
        with open(file) as f:
            for line in f:
                if line.strip() != "":
                    a, b = line.split(":", 1)
                    self.add_category(a.strip(), b.strip(), f"{a.strip()}.html")

    def load_implementations(self, file):
        with open(file) as f:
            self.implementations = yaml.load(f, Loader=yaml.FullLoader)

    def load_families(self, file):
        with open(file) as f:
            self.families = yaml.load(f, Loader=yaml.FullLoader)
        for t in self.families:
            for i in self.families[t]:
                self.families[t][i]["elements"] = {}

    def load_references(self, file):
        with open(file) as f:
            for line in f:
                if line.strip() != "":
                    self.add_reference(line.strip(), f"{line.strip()}.html")

    def load_folder(self, folder):
        for file in os.listdir(folder):
            if file.endswith(".def") and not file.startswith("."):
                with open(os.path.join(folder, file)) as f:
                    data = yaml.load(f, Loader=yaml.FullLoader)

                fname = file[:-4]

                self.add_element(Element(data, fname))

        if settings.github_token is None:
            warnings.warn("Building without GitHub token. Timestamps will not be obtained.")
        else:
            g = Github(settings.github_token)
            repo = g.get_repo("mscroggs/defelement.com")
            for e in self.elements:
                commits = repo.get_commits(path=f"elements/{e.filename}.def")
                try:
                    e.created = commits.get_page(-1)[-1].commit.committer.date
                    e.modified = commits.get_page(0)[0].commit.committer.date
                except IndexError:
                    e.created = datetime.now()
                    e.modified = datetime.now()

        self.elements.sort(key=lambda x: x.name.lower())

    def add_family(self, t, e, name, fname):
        if len(e.split(",")) == 3:
            i, j, k = e.split(",")
        else:
            i, j, k, _ = e.split(",")
        if t not in self.families:
            self.families[t] = {}
            warnings.warn(f"Complex type included in familes data: {t}")
        if i not in self.families[t]:
            warnings.warn(f"Family not included in familes data: {i}")
            self.families[t][i] = {"elements": {}}
        if k not in self.families[t][i]["elements"]:
            self.families[t][i]["elements"][k] = {}
        self.families[t][i]["elements"][k][j] = (name, fname)

    def add_reference(self, e, fname):
        self.references[e] = fname

    def add_category(self, fname, cname, html_filename):
        self.categories[fname] = (cname, html_filename)

    def get_category_name(self, c):
        return self.categories[c][0]

    def get_space_name(self, element, link=True):
        for e in self.elements:
            if e.filename == element:
                if link:
                    return e.html_link
                else:
                    return e.html_name
                break
        raise ValueError(f"Could not find space: {element}")

    def get_element(self, ename):
        for e in self.elements:
            if e.name == ename:
                return e
        raise ValueError(f"Could not find element: {ename}")

    def add_element(self, e):
        self.elements.append(e)
        e._c = self
        for r in e.reference_elements(False):
            assert r in self.references

        for j, k in e.complexes(False, False).items():
            for i in k:
                self.add_family(j, i, e.html_name, e.html_filename)

    def elements_in_category(self, c):
        return [e for e in self.elements if c in e.categories(False, False)]

    def elements_in_implementation(self, i):
        return [e for e in self.elements if e.implemented(i)]

    def elements_by_reference(self, r):
        return [e for e in self.elements if r in e.reference_elements(False)]


class Element:
    def __init__(self, data, fname):
        self.data = data
        self.filename = fname
        self._c = None
        self.created = None
        self.modified = None

    def name_with_variant(self, variant):
        if variant is None:
            return self.name
        return f"{self.name} ({self.variant_name(variant)} variant)"

    def variant_name(self, variant):
        return self.data["variants"][variant]["variant-name"]

    def variants(self):
        if "variants" not in self.data:
            return []
        return [
            f"{v['variant-name']}: {v['description']}"
            for v in self.data["variants"].values()
        ]

    def min_order(self, ref):
        if "min-order" not in self.data:
            return 0
        if isinstance(self.data["min-order"], dict):
            return self.data["min-order"][ref]
        return self.data["min-order"]

    def max_order(self, ref):
        if "max-order" not in self.data:
            return None
        if isinstance(self.data["max-order"], dict):
            return self.data["max-order"][ref]
        return self.data["max-order"]

    def reference_elements(self, link=True):
        if link:
            return [f"<a href='/lists/references/{e}.html'>{e}</a>"
                    for e in self.data["reference-elements"]]
        else:
            return self.data["reference-elements"]

    def alternative_names(
        self, include_bracketed=True, include_complexes=True, include_variants=True, link=True,
        strip_cell_name=False, cell=None
    ):
        if "alt-names" not in self.data:
            return []
        out = self.data["alt-names"]
        if include_complexes:
            out += self.family_names(link=link)
        if include_variants and "variants" in self.data:
            for v in self.data["variants"].values():
                if "names" in v:
                    out += [f"{i} ({v['variant-name']} variant)" for i in v["names"]]

        if include_bracketed:
            out = [i[1:-1] if i[0] == "(" and i[-1] == ")" else i
                   for i in out]
        else:
            out = [i for i in out if i[0] != "(" or i[-1] != ")"]

        if cell is not None:
            out = [i for i in out if " (" not in i or cell in i]

        if strip_cell_name:
            out = [i.split(" (")[0] for i in out]

        return out

    def short_names(self, include_variants=True):
        out = []
        if "short-names" in self.data:
            out += self.data["short-names"]
        if include_variants and "variants" in self.data:
            for v in self.data["variants"].values():
                if "short-names" in v:
                    out += [f"{i} ({v['variant-name']} variant)" for i in v["short-names"]]
        return out

    def mapping(self):
        if "mapping" not in self.data:
            return None
        return self.data["mapping"]

    def sobolev(self):
        if "sobolev" not in self.data:
            return None
        return self.data["sobolev"]

    def complexes(self, link=True, names=True):
        if "complexes" not in self.data:
            return {}

        out = {}
        com = self.data["complexes"]
        for key, families in com.items():
            out[key] = []
            if not isinstance(families, (list, tuple)):
                families = [families]
            for e in families:
                if names:
                    namelist = []
                    e_s = e.split(",")
                    if len(e_s) == 3:
                        fam, ext, cell = e_s
                        k = "k"
                    else:
                        fam, ext, cell, k = e_s
                    data = self._c.families[key][fam]
                    for key2, f in keys_and_names:
                        if key2 in data:
                            namelist.append("\\(" + f(data[key2], ext, cell, k) + "\\)")
                    entry = ""
                    if link:
                        entry = f"<a class='nou' href='/families/{fam   }.html'>"
                    entry += " / ".join(namelist)
                    if link:
                        entry += "</a>"
                    out[key].append(entry)
                else:
                    out[key].append(e)
        return out

    def order_range(self):
        def make_order_data(min_o, max_o):
            if isinstance(min_o, dict):
                orders = []
                for i, min_i in min_o.items():
                    if isinstance(max_o, dict) and i in max_o:
                        orders.append(i + ": " + make_order_data(min_i, max_o[i]))
                    else:
                        orders.append(i + ": " + make_order_data(min_i, max_o))
                return "<br />\n".join(orders)
            if max_o is None:
                return f"\\({min_o}\\leqslant k\\)"
            if max_o == min_o:
                return f"\\(k={min_o}\\)"
            return f"\\({min_o}\\leqslant k\\leqslant {max_o}\\)"

        return make_order_data(
            self.data["min-order"] if "min-order" in self.data else 0,
            self.data["max-order"] if "max-order" in self.data else None)

    def sub_elements(self, link=True):
        assert self.is_mixed
        out = []
        for e in self.data["mixed"]:
            element, order = e.split("(")
            order = order.split(")")[0]
            space_link = self._c.get_space_name(element, link=link)
            out.append(f"<li>order \\({order}\\) {space_link} space</li>")
        return out

    def make_dof_descriptions(self):
        if "dofs" not in self.data:
            return ""

        def dofs_on_entity(entity, dofs):
            if not isinstance(dofs, str):
                doflist = [dofs_on_entity(entity, d) for d in dofs]
                return ",<br />".join(doflist[:-1]) + ", and " + doflist[-1]
            if "integral moment" in dofs:
                mom_type, space_info = dofs.split(" with ")
                space_info = space_info.strip()
                if space_info.startswith("{") and space_info.endswith("}"):
                    return f"{mom_type} with \\(\\left\\{{{space_info[1:-1]}\\right\\}}\\)"
                if space_info.startswith('"') and space_info.endswith('"'):
                    return f"{mom_type} with {insert_links(space_info[1:-1])}"

                assert space_info.startswith("(") and space_info.endswith(")")
                space_info = space_info[1:-1]
                space, order = space_info.split(",")
                space = space.strip()
                order = order.strip()
                space_link = self._c.get_space_name(space)
                return f"{mom_type} with an order \\({order}\\) {space_link} space"
            return dofs

        def make_dof_d(data, post=""):
            dof_data = []
            for i in ["interval", "triangle", "tetrahedron", "quadrilateral", "hexahedron"]:
                if i in data:
                    dof_data.append(make_dof_d(data[i], f" ({i})"))
            if len(dof_data) != 0:
                return "<br />\n<br />\n".join(dof_data)

            for i, j in [
                ("On each vertex", "vertices"),
                ("On each edge", "edges"),
                ("On each face", "faces"),
                ("On each volume", "volumes"),
                ("On each ridge", "ridges"),
                ("On each peak", "peaks"),
                ("On each facet", "facets"),
                ("On the interior of the reference element", "cell"),
            ]:
                if j in data:
                    if isinstance(data[j], dict):
                        for shape, sub_data in data[j].items():
                            dof_data.append(f"{i} ({shape}){post}: {dofs_on_entity(j, sub_data)}")
                    else:
                        dof_data.append(f"{i}{post}: {dofs_on_entity(j, data[j])}")
            return "<br />\n".join(dof_data)

        return make_dof_d(self.data["dofs"])

    def make_polynomial_set_html(self):
        # TODO: move some of this to polynomial file
        if "polynomial-set" not in self.data:
            return []
        psets = {}
        for i, j in self.data["polynomial-set"].items():
            if j not in psets:
                psets[j] = []
            psets[j].append(i)
        if (
            "reference-elements" in self.data and len(psets) == 1
            and len(list(psets.values())[0]) == len(self.data["reference-elements"])
        ):
            out = f"\\({make_poly_set(list(psets.keys())[0])}\\)<br />"
        else:
            out = ""
            for i, j in psets.items():
                out += f"\\({make_poly_set(i)}\\) ({', '.join(j)})<br />\n"
        extra = make_extra_info(" && ".join(psets.keys()))
        if len(extra) > 0:
            out += "<a id='show_pset_link' href='javascript:show_psets()'"
            out += " style='display:block'>"
            out += "&darr; Show polynomial set definitions &darr;</a>"
            out += "<a id='hide_pset_link' href='javascript:hide_psets()'"
            out += " style='display:none'>"
            out += "&uarr; Hide polynomial set definitions &uarr;</a>"
            out += "<div id='psets' style='display:none'>"
            out += extra
            out += "</div>"
            out += "<script type='text/javascript'>\n"
            out += "function show_psets(){\n"
            out += "  document.getElementById('show_pset_link').style.display = 'none'\n"
            out += "  document.getElementById('hide_pset_link').style.display = 'block'\n"
            out += "  document.getElementById('psets').style.display = 'block'\n"
            out += "}\n"
            out += "function hide_psets(){\n"
            out += "  document.getElementById('show_pset_link').style.display = 'block'\n"
            out += "  document.getElementById('hide_pset_link').style.display = 'none'\n"
            out += "  document.getElementById('psets').style.display = 'none'\n"
            out += "}\n"
            out += "</script>"
        return out

    def dof_counts(self):
        if "ndofs" not in self.data:
            return ""
        return make_dof_data(self.data["ndofs"])

    def entity_dof_counts(self):
        if "entity-ndofs" not in self.data:
            return ""
        return make_dof_data(self.data["entity-ndofs"])

    @property
    def name(self):
        return self.data["name"]

    @property
    def notes(self):
        if "notes" not in self.data:
            return []
        return self.data["notes"]

    @property
    def html_name(self):
        if "html-name" in self.data:
            return self.data["html-name"]
        else:
            return self.data["name"]

    @property
    def html_filename(self):
        return f"{self.filename}.html"

    @property
    def is_mixed(self):
        return "mixed" in self.data

    @property
    def html_link(self):
        return f"<a href='/elements/{self.html_filename}'>{self.html_name}</a>"

    def implemented(self, lib):
        return "implementations" in self.data and lib in self.data["implementations"]

    def get_implementation_string(self, lib, reference, variant=None):
        assert self.implemented(lib)
        if variant is None:
            data = self.data["implementations"][lib]
        else:
            if variant not in self.data["implementations"][lib]:
                raise VariantNotImplemented()
            data = self.data["implementations"][lib][variant]
        if isinstance(data, dict):
            if reference not in data:
                return None, {}
            out = data[reference]
        else:
            out = data
        params = {}
        if "=" in out:
            sp = out.split("=")
            out = " ".join(sp[0].split(" ")[:-1])
            sp[-1] += " "
            for i, j in zip(sp[:-1], sp[1:]):
                i = i.split(" ")[-1]
                j = " ".join(j.split(" ")[:-1])
                params[i] = j

        return out, params

        if " variant=" in out:
            return out.split(" variant=")
        return out, None

    def list_of_implementation_strings(self, lib, joiner="<br />"):
        assert self.implemented(lib)

        if "display" in self.data["implementations"][lib]:
            d = implementations.formats[lib](self.data["implementations"][lib]["display"], {})
            return f"<code>{d}</code>"
        if "variants" in self.data:
            variants = self.data["variants"]
        else:
            variants = {None: {}}

        i_dict = {}
        for v, vinfo in variants.items():
            if v is None:
                data = self.data["implementations"][lib]
            else:
                if v not in self.data["implementations"][lib]:
                    continue
                data = self.data["implementations"][lib][v]
            if isinstance(data, str):
                s = implementations.formats[lib](*self.get_implementation_string(lib, None, v))
                if s not in i_dict:
                    i_dict[s] = []
                if v is None:
                    i_dict[s].append("")
                else:
                    i_dict[s].append(vinfo["variant-name"])
            else:
                for i, j in data.items():
                    s = implementations.formats[lib](*self.get_implementation_string(lib, i, v))
                    if s not in i_dict:
                        i_dict[s] = []
                    if v is None:
                        i_dict[s].append(i)
                    else:
                        i_dict[s].append(f"{i}, {vinfo['variant-name']}")
        if len(i_dict) == 1:
            return f"<code>{list(i_dict.keys())[0]}</code>"
        imp_list = [f"<code>{i}</code> <span style='font-size:60%'>({'; '.join(j)})</span>"
                    for i, j in i_dict.items()]
        if joiner is None:
            return imp_list
        else:
            return joiner.join(imp_list)

    def make_implementation_examples(self, lib):
        return implementations.examples[lib](self)

    def has_implementation_examples(self, lib):
        return lib in implementations.examples

    def categories(self, link=True, map_name=True):
        if "categories" not in self.data:
            return []
        if map_name:
            cnames = {c: self._c.get_category_name(c) for c in self.data["categories"]}
        else:
            cnames = {c: c for c in self.data["categories"]}
        if link:
            return [f"<a href='/lists/categories/{c}.html'>{cnames[c]}</a>"
                    for c in self.data["categories"]]
        else:
            return [f"{cnames[c]}" for c in self.data["categories"]]

    def references(self):
        references = self.data["references"] if "references" in self.data else []

        if "complexes" in self.data:
            for key, families in self.data["complexes"].items():
                if not isinstance(families, (list, tuple)):
                    families = [families]
                for e in families:
                    e_s = e.split(",")
                    if len(e_s) == 3:
                        fam, ext, cell = e_s
                        k = "k"
                    else:
                        fam, ext, cell, k = e_s
                    data = self._c.families[key][fam]
                    if "arnold-logg" in data and arnold_logg_reference not in references:
                        references.append(arnold_logg_reference)
                    if "cockburn-fu" in data and cockburn_fu_reference not in references:
                        references.append(cockburn_fu_reference)
                    if "references" in data:
                        for r in references:
                            if r not in references:
                                references.append(r)
        return references

    @property
    def test(self):
        return "test" in self.data

    @property
    def has_examples(self):
        return "examples" in self.data

    @property
    def examples(self):
        if "examples" not in self.data:
            return []
        return self.data["examples"]
