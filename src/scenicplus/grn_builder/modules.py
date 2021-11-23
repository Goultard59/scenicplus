from ..scenicplus_class import SCENICPLUS
import attr
from typing import List, Tuple
from collections import namedtuple
from itertools import chain
from tqdm import tqdm
from ..utils import cistarget_results_to_TF2R, Groupby
import numpy as np

flatten_list = lambda t: [item for sublist in t for item in sublist]

#HARDCODED VARIABLES
RHO_THRESHOLD = 0.03
TARGET_REGION_NAME = 'region'
TARGET_GENE_NAME = 'target'
IMPORTANCE_SCORE_NAME = 'importance'
CORRELATION_COEFFICIENT_NAME = 'rho'

REGIONS2GENES_HEADER = (TARGET_REGION_NAME, TARGET_GENE_NAME, IMPORTANCE_SCORE_NAME, CORRELATION_COEFFICIENT_NAME)

@attr.s(repr=False)
class eRegulon():
    """
    An eRegulon is a gene signature that defines the target regions and genes of a Transcription Factor (TF).
    """

    transcription_factor = attr.ib(type = str)
    regions2genes = attr.ib(type = List[namedtuple])
    #optional
    context = attr.ib(default = frozenset())
    in_leading_edge = attr.ib(type = List[bool], default = None)
    gsea_enrichment_score = attr.ib(type = float, default = None)
    gsea_pval = attr.ib(type = float, default = None)
    gsea_adj_pval = attr.ib(type = float, default = None)
    @regions2genes.validator
    def validate_regions2genes_header(self, attribute, value):
        if value is not None:
            if all([getattr(v, '_fields', None) == None for v in value]):
                Warning("{} genes2weights should be a list of named tuples".format(self.transcription_factor))
            if not all([v._fields == REGIONS2GENES_HEADER for v in value]):
                Warning("{} names of regions2genes should be: {}".format(self.transcription_factor, REGIONS2GENES_HEADER))
    
    @regions2genes.validator
    def validate_correlation_coef_same_sign(self, attribute, value):
        if value is not None:
            correlation_coefficients = [getattr(v, CORRELATION_COEFFICIENT_NAME) for v in value]
            if not (all([cc <= 0 for cc in correlation_coefficients]) or all([cc >= 0 for cc in correlation_coefficients])):
                Warning("{} correlation coefficients of regions to genes should all have the same sign".format(self.transcription_factor))
    
    @in_leading_edge.validator
    def validate_length(self, attribute, value):
        if value is not None:
            if not len(value) == self.n_target_genes:
                Warning(f"in_leading_edge ({len(value)}) should have the same length as the number of target genes ({self.n_target_genes})")

    @property
    def target_genes(self):
        """
        Return target genes of this eRegulon.
        """
        return list(set([ getattr(r2g, TARGET_GENE_NAME) for r2g in self.regions2genes ]))
    
    @property
    def target_regions(self):
        """
        Return target regions of this eRegulon.
        """
        return list(set([ getattr(r2g, TARGET_REGION_NAME) for r2g in self.regions2genes ]))
    
    @property
    def n_target_genes(self):
        """
        Return number of target genes.
        """
        return len(self.target_genes)
    
    @property
    def n_target_regions(self):
        """
        Return number of target regions.
        """
        return len(self.target_regions)

    def subset_leading_edge(self, inplace = True):
        if self.in_leading_edge is not None and self.gsea_enrichment_score is not None:
            regions2genes_subset = [
                r2g for r2g, in_le in  zip(self.regions2genes, self.in_leading_edge)
                if in_le]
            
            in_leading_edge_subset = [
                in_le for in_le in self.in_leading_edge
                if in_le
            ]
            if inplace:
                self.regions2genes = regions2genes_subset
                self.in_leading_edge = in_leading_edge_subset
            else:
                return eRegulon(
                    transcription_factor = self.transcription_factor,
                    context = self.context,
                    regions2genes = regions2genes_subset,
                    in_leading_edge = in_leading_edge_subset,
                    gsea_enrichment_score = self.gsea_enrichment_score,
                    gsea_pval = self.gsea_pval,
                    gsea_adj_pval = self.gsea_adj_pval)
        else:
            Warning('Leading edge not defined!')
    
    def __repr__(self) -> str:
        descr = f"eRegulon for TF {self.transcription_factor} in context {self.context}."
        descr += f"\n\tThis eRegulon has {self.n_target_regions} target regions and {self.n_target_genes} target genes."
        return descr

def quantile_thr(adjacencies, grouped, threshold, min_regions_per_gene,  context = frozenset()):

    def _qt(x):
        #function to return threshold_quantile from a vector
        return np.quantile(x, threshold)
    
    def _gt(x):
        #function to check minimum regions requirement
        if sum(x) >= min_regions_per_gene:
            return x
        else:
            return np.repeat(False, len(x))
    
    c = frozenset(["{} quantile".format(threshold)]).union(context)
    #grouped = Groupby(adjacencies[TARGET_GENE_NAME].to_numpy()) #this could be moved out of the function
    importances = adjacencies[IMPORTANCE_SCORE_NAME].to_numpy()
    
    #get quantiles and threshold
    thresholds = grouped.apply(_qt, importances, True)
    passing = importances > thresholds

    if min_regions_per_gene > 0:
        #check min regions per gene
        passing = grouped.apply(_gt, passing, True).astype(bool)

    if sum(passing) > 0:
        yield c, adjacencies.loc[passing].reset_index(drop = True)

def top_targets(adjacencies, grouped, n, min_regions_per_gene, context = frozenset()):

    def _top(x):
        #function to get top n entries. 
        if len(x) >= n:
            return min(np.sort(x)[-n:])
        else:
            return min(x)
    
    def _gt(x):
        #function to check minimum regions requirement
        if sum(x) >= min_regions_per_gene:
            return x
        else:
            return np.repeat(False, len(x))

    c = frozenset(["Top {} region-to-gene links per gene".format(n)]).union(context)
    #grouped = Groupby(adjacencies[TARGET_GENE_NAME].to_numpy()) #this could be moved out of the function
    importances = adjacencies[IMPORTANCE_SCORE_NAME].to_numpy()

    #get top n threshold
    thresholds = grouped.apply(_top, importances, True)
    passing = importances >= thresholds

    if min_regions_per_gene > 0:
        #check min regions per gene
        passing = grouped.apply(_gt, passing, True).astype(bool)

    if sum(passing) > 0:
        yield c, adjacencies.loc[passing].reset_index(drop = True)

def top_regions(adjacencies, grouped, n, min_regions_per_gene, context = frozenset()):

    def _top(x):
        #function to get top n entries. 
        if len(x) >= n:
            return min(np.sort(x)[-n:])
        else:
            return min(x)
    
    def _gt(x):
        #function to check minimum regions requirement
        if sum(x) >= min_regions_per_gene:
            return x
        else:
            return np.repeat(False, len(x))

    c = frozenset(["Per region top {} region-to-gene links per gene".format(n)]).union(context)

    #grouped = Groupby(adjacencies[TARGET_REGION_NAME].to_numpy()) #this could be moved out of the function
    importances = adjacencies[IMPORTANCE_SCORE_NAME].to_numpy()
    
    #get top n threshold
    thresholds = grouped.apply(_top, importances, True)
    passing = importances >= thresholds

    df = adjacencies.loc[passing].reset_index(drop = True)

    if min_regions_per_gene > 0:
        #check minimum target gene requirement
        grouped = Groupby(df[TARGET_GENE_NAME].to_numpy())
        passing = grouped.apply(_gt, passing[passing], True).astype(bool)
        df = df.loc[passing].reset_index(drop = True)

    if len(df) > 0:
        yield c, df

def binarize_BASC(adjacencies, grouped, min_regions_per_gene, context = frozenset()):
    from ..BASCA import binarize

    def _binarize_basc(x):
        if len(x) > 2:
            return binarize(x, calc_p=False).threshold
        else:
            # can only binarize when array is > 2
            return 0
    
    def _gt(x):
        #function to check minimum regions requirement
        if sum(x) >= min_regions_per_gene:
            return x
        else:
            return np.repeat(False, len(x))

    c = frozenset(["BASC binarized"]).union(context)

    importances = adjacencies[IMPORTANCE_SCORE_NAME].to_numpy()
    
    #get BASC thresholds
    thresholds = grouped.apply(_binarize_basc, importances, True)
    passing = importances > thresholds

    if min_regions_per_gene > 0:
        #check min regions per gene
        passing = grouped.apply(_gt, passing, True).astype(bool)

    if sum(passing) > 0:
        yield c, adjacencies.loc[passing].reset_index(drop = True)

def create_emodules(SCENICPLUS_obj: SCENICPLUS,
                    region_to_gene_key = 'region_to_gene',
                    thresholds = (0.75, 0.90),
                    top_n_target_genes = (50, 100),
                    top_n_target_regions = (),
                    binarize_basc = False,
                    min_regions_per_gene = 5,
                    rho_dichotomize=True,
                    keep_only_activating=False,
                    rho_threshold=RHO_THRESHOLD,
                    keep_extended_motif_annot = False) -> Tuple[List[str], List[eRegulon]]:
    #check input
    if region_to_gene_key not in SCENICPLUS_obj.uns.keys():
        raise ValueError('Calculate region to gene relationships first.')
    def iter_thresholding(adj, context):
        grouped_adj_by_gene = Groupby(adj[TARGET_GENE_NAME].to_numpy())
        grouped_adj_by_region = Groupby(adj[TARGET_REGION_NAME].to_numpy())
        yield from chain(
            chain.from_iterable(quantile_thr(adjacencies = adj, 
                                             grouped = grouped_adj_by_gene, 
                                             threshold = thr, 
                                             min_regions_per_gene = min_regions_per_gene, 
                                             context = context) for thr in thresholds),

            chain.from_iterable(top_targets(adjacencies = adj, 
                                            grouped = grouped_adj_by_gene, 
                                            n = n, 
                                            min_regions_per_gene = min_regions_per_gene,  
                                            context = context) for n in top_n_target_genes),

            chain.from_iterable(top_regions(adjacencies = adj, 
                                            grouped = grouped_adj_by_region, 
                                            n = n, 
                                            min_regions_per_gene = min_regions_per_gene, 
                                            context = context) for n in top_n_target_regions),
            binarize_BASC(adjacencies = adj,
                          grouped = grouped_adj_by_gene,
                          min_regions_per_gene = min_regions_per_gene,
                          context = context) if binarize_basc else []
        )

    if rho_dichotomize:
        #split positive and negative correlation coefficients
        repressing_adj = SCENICPLUS_obj.uns[region_to_gene_key].loc[
            SCENICPLUS_obj.uns[region_to_gene_key][CORRELATION_COEFFICIENT_NAME] < -rho_threshold]
        activating_adj = SCENICPLUS_obj.uns[region_to_gene_key].loc[
            SCENICPLUS_obj.uns[region_to_gene_key][CORRELATION_COEFFICIENT_NAME] >  rho_threshold]
        r2g_iter = chain(
                iter_thresholding(repressing_adj, frozenset(['negative r2g'])),
                iter_thresholding(activating_adj, frozenset(['positive r2g'])),
            )
    else:
        #don't split
        if keep_only_activating:
            r2g_iter = iter_thresholding(SCENICPLUS_obj.uns[region_to_gene_key].loc[
                SCENICPLUS_obj.uns[region_to_gene_key][CORRELATION_COEFFICIENT_NAME] >  rho_threshold])
        else:
            r2g_iter = iter_thresholding(SCENICPLUS_obj.uns[region_to_gene_key])

    #merge all cistarget results
    ctx_results = flatten_list([[SCENICPLUS_obj.menr[x][y] for y in SCENICPLUS_obj.menr[x].keys()] for x in SCENICPLUS_obj.menr.keys()])
    tfs_to_regions_d = cistarget_results_to_TF2R(ctx_results, keep_extended = keep_extended_motif_annot)
    #iterate over all thresholdings and generate eRegulons
    n_params = sum([len(thresholds), len(top_n_target_genes), len(top_n_target_regions)])
    total_iter = (2 * (n_params + (binarize_basc * 1)) )  if rho_dichotomize else (n_params + (binarize_basc * 1))
    eRegulons = []
    for context, r2g_df in tqdm(r2g_iter, total = total_iter):
        for transcription_factor in tfs_to_regions_d.keys():
            regions_enriched_for_TF_motif = set(tfs_to_regions_d[transcription_factor])
            try:
                r2g_df_enriched_for_TF_motif = r2g_df.loc[ [ region in regions_enriched_for_TF_motif for region in r2g_df[TARGET_REGION_NAME] ] ]
            except:
                print(r2g_df)
            if len(r2g_df_enriched_for_TF_motif) > 0:
                eRegulons.append(
                    eRegulon(
                        transcription_factor = transcription_factor,
                        regions2genes = list(r2g_df_enriched_for_TF_motif[list(REGIONS2GENES_HEADER)].itertuples(index = False, name = 'r2g')),
                        context = context))
    return set(tfs_to_regions_d), eRegulons

def _merge_single_TF(l_e_modules):
    transcription_factor = set([em.transcription_factor for em in l_e_modules])
    if len(transcription_factor) > 1:
        raise ValueError('l_e_modules should only contain a single TF')
    else:
        transcription_factor = list(transcription_factor)[0]

    regions2genes_merged = list( set( flatten_list([em.regions2genes for em in  np.array(l_e_modules)]) ) )
    context = frozenset(flatten_list([em.context for em in l_e_modules]))
    return eRegulon(
        transcription_factor = transcription_factor,
        regions2genes = regions2genes_merged,
        context = context)

def _merge_across_TF(l_e_modules):
    l_e_modules = np.array(l_e_modules)
    TFs = [em.transcription_factor for em in l_e_modules]
    grouped = Groupby(TFs)
    for idx in grouped.indices:
        yield _merge_single_TF(l_e_modules[idx])
    
def merge_emodules(SCENICPLUS_obj: SCENICPLUS = None,
                   e_modules: list = None,
                   e_modules_key: str = 'eRegulons',
                   rho_dichotomize: bool = True,
                   key_to_add: str = 'eRegulons',
                   inplace: bool = True):
    #check input
    if SCENICPLUS_obj is not None:
        if e_modules_key not in SCENICPLUS_obj.uns.keys():
            raise ValueError(f'No e-modules found under key: {e_modules_key}.')
    
    e_modules = SCENICPLUS_obj.uns[e_modules_key] if SCENICPLUS_obj is not None else e_modules

    if rho_dichotomize:
        TF2G_pos_R2G_pos_ems = [em for em in e_modules if ('positive tf2g' in em.context and 'positive r2g' in em.context)]
        TF2G_pos_R2G_neg_ems = [em for em in e_modules if ('positive tf2g' in em.context and 'negative r2g' in em.context)]
        TF2G_neg_R2G_pos_ems = [em for em in e_modules if ('negative tf2g' in em.context and 'positive r2g' in em.context)]
        TF2G_neg_R2G_neg_ems = [em for em in e_modules if ('negative tf2g' in em.context and 'negative r2g' in em.context)]

        iter_merger = chain(
            _merge_across_TF(TF2G_pos_R2G_pos_ems),
            _merge_across_TF(TF2G_pos_R2G_neg_ems),
            _merge_across_TF(TF2G_neg_R2G_pos_ems),
            _merge_across_TF(TF2G_neg_R2G_neg_ems)
        )
    else:
        iter_merger = chain(
            _merge_across_TF(e_modules)
        )
    
    if inplace:
        SCENICPLUS_obj.uns[key_to_add] = [eReg for eReg in iter_merger]
    else:
        return [eReg for eReg in iter_merger]

