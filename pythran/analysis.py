from tables import modules
import ast
import networkx as nx

##
class ImportedIds(ast.NodeVisitor):
    """ Gather ids referenced by a node """
    def __init__(self, global_declarations):
        self.references=set()
        self.global_declarations=set(global_declarations)
        self.skip=set()

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.skip.add(node.id)
        elif node.id not in self.skip and node.id not in self.global_declarations:
            self.references.add(node.id)

    def visit_FunctionDef(self, node):
        local = ImportedIds(self.global_declarations)
        [local.visit(n) for n in node.body]
        local.references -= { arg.id for arg in node.args.args }
        self.global_declarations.add(node.name)
        self.references.update(local.references)

    def visit_ListComp(self, node):
        local = ImportedIds(self.global_declarations)
        [ local.visit(n) for n in node.generators ]
        local.visit(node.elt)
        self.references.update(local.references)

    def visit_Lambda(self, node):
        local = ImportedIds(self.global_declarations)
        local.visit(node.body)
        local.references -= { arg.id for arg in node.args.args }
        self.references.update(local.references)

    def visit_ImportFrom(self, node):
        self.global_declarations.update({ alias.name:None for alias in node.names})

def imported_ids(node, global_declarations):
    r = ImportedIds(global_declarations)
    if isinstance(node,list):
        node=ast.If(ast.Num(1),node,None)
    r.visit(node)
    #*** expand all modules here
    return { ref for ref in r.references } - set(modules["__builtins__"].keys()+[ "True", "False" ])

##
class WrittenAreas(ast.NodeVisitor):
    def __init__(self):
        self.written_areas=set()
        self.aliases=dict()
        self.deps=set()

    def recursievely_gather_aliases(self, id, target):
        if isinstance(target, ast.Name):
            self.aliases[ id ].add(target.id)
        elif isinstance(target, ast.Subscript):
            self.recursievely_gather_aliases(id, target.value)

    def visit_FunctionDef(self, node):
        self.aliases={ arg.id:{arg.id} for arg in node.args.args }
        [ self.visit(b) for b in node.body ]

    def visit_Assign(self, node):
        all_parameters=reduce(set.union, [ s for s in self.aliases.itervalues() ], set() )
        if isinstance(node.value, ast.Name) and node.value.id in all_parameters:
            for target in node.targets:
                self.recursievely_gather_aliases(node.value.id, target)
        else:
            [self.visit(t) for t in node.targets]
        self.visit(node.value)

    def visit_AugAssign(self, node):
        all_parameters=reduce(set.union, [ s for s in self.aliases.itervalues() ], set() )
        if isinstance(node.value, ast.Name) and node.value.id in all_parameters:
            self.recursievely_gather_aliases(node.value.id, node.target)
        else:
            self.visit(node.target)
        self.visit(node.value)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            for aliases in self.aliases.itervalues():
                if node.id in aliases:
                    self.written_areas.update(aliases)

    def visit_Subscript(self, node):
        if isinstance(node.ctx, ast.Store):
            tmp = node.value
            while isinstance(tmp, ast.Subscript):
                tmp=tmp.value
            if not isinstance(tmp, ast.Name):
                raise NotImplementedError("assigning to a subscript whose value is not an identifier but an '{0}'".format(type(tmp)))
            for aliases in self.aliases.itervalues():
                if tmp.id in aliases:
                    self.written_areas.update(aliases)

    def visit_Call(self, node):
        assert isinstance(node.func, ast.Name)
        [self.visit(arg) for arg in node.args]
        imported_areas=imported_ids(node, dict())
        imported_areas.difference_update({ node.func.id })
        all_parameters=reduce(set.union, [ s for s in self.aliases.itervalues() ], set() )
        if not imported_areas.isdisjoint(all_parameters):
            self.deps.add(node.func.id)


def written_areas(node):
    wv = WrittenAreas()
    wv.visit(node)
    return wv.written_areas, wv.deps

class PurityTest(ast.NodeVisitor):
    """ Gathers function purity information """
    def __init__(self):
        self.pure=nx.DiGraph()

    def visit_Module(self, node):
        [self.visit(n) for n in node.body ]
        painted=1
        while painted:
            painted=0
            for fun in self.pure:
                for s in self.pure.successors(fun):
                    if not self.pure.node[s]["pure"] and self.pure.node[fun]["pure"]:
                        painted+=1
                        self.pure.node[fun]["pure"]=False

    def visit_Lambda(self, node):
        self.visit_FunctionDef(self,node)

    def visit_FunctionDef(self, node):
        weffects, wdeps = written_areas(node)
        imported_areas = imported_ids(node.body,dict())
        self.pure.add_node(node.name, pure=(imported_areas.isdisjoint(weffects)))
        [self.pure.add_node(wd, pure="unknown") for wd in wdeps if wd not in self.pure]
        [ self.pure.add_edge(node.name, wd) for wd in wdeps ]

def purity_test(node):
    pt=PurityTest()
    pt.visit(node)
    #nx.write_dot(pt.pure,"pure.dot")
    #for p in pt.pure:
    #    print p, "is pure?", pt.pure.node[p]["pure"] 
    return { p for p in pt.pure if pt.pure.node[p]["pure"] }
