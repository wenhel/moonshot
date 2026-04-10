"""
核心接口定义模块
定义了 Labeler 系统的基础抽象接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
import json

if TYPE_CHECKING:
    from PIL import Image


@dataclass
class LabelerInput:
    """标准化的 Labeler 输入格式

    Supports both:
    - Legacy path-based input: image_path/image_paths (strings)
    - New PIL-based input: images (List[PIL.Image.Image])

    Use from_assembled() to convert from AssembledInput.
    """
    text: str
    # Legacy path-based fields
    image_path: Optional[str] = None
    image_paths: Optional[List[str]] = None
    # New PIL-based field
    images: Optional[List["Image.Image"]] = None
    # Instruction field (from PromptProcessor)
    instruction: Optional[str] = None
    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None
    # Sample identification
    sample_id: Optional[str] = None
    label: Optional[int] = None
    label_str: Optional[str] = None
    topic: Optional[str] = None

    @classmethod
    def from_legacy_args(cls, tweet_text: str, image_path: Optional[str] = None,
                        image_paths: Optional[List[str]] = None, **kwargs) -> 'LabelerInput':
        """从旧版本参数创建输入对象，保持兼容性"""
        return cls(
            text=tweet_text,
            image_path=image_path,
            image_paths=image_paths,
            metadata=kwargs
        )

    @property
    def has_images(self) -> bool:
        """Check if this input has any images (either PIL or path-based)."""
        if self.images:
            return len(self.images) > 0
        if self.image_paths:
            return len(self.image_paths) > 0
        if self.image_path:
            return True
        return False

    @property
    def num_images(self) -> int:
        """Get number of images."""
        if self.images:
            return len(self.images)
        if self.image_paths:
            return len(self.image_paths)
        if self.image_path:
            return 1
        return 0

    def get_images_pil(self) -> List["Image.Image"]:
        """Get images as PIL Image objects.

        Loads from paths if only paths are provided.

        Returns:
            List of PIL Image objects
        """
        if self.images:
            return self.images

        from PIL import Image as PILImage

        if self.image_paths:
            return [PILImage.open(p) for p in self.image_paths]
        if self.image_path:
            return [PILImage.open(self.image_path)]
        return []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'text': self.text,
            'image_path': self.image_path,
            'image_paths': self.image_paths,
            'has_images': self.has_images,
            'num_images': self.num_images,
            'instruction': self.instruction,
            'sample_id': self.sample_id,
            'label': self.label,
            'label_str': self.label_str,
            'topic': self.topic,
            'metadata': self.metadata or {}
        }


@dataclass
class LabelerOutput:
    """标准化的 Labeler 输出格式"""
    result: Dict[str, Any]
    cached: bool = False
    processing_time: float = 0.0
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_legacy_dict(self) -> Dict[str, Any]:
        """转换为旧版本返回格式，保持兼容性"""
        return self.result
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为完整字典格式"""
        return {
            'result': self.result,
            'cached': self.cached,
            'processing_time': self.processing_time,
            'error': self.error,
            'metadata': self.metadata or {},
            'timestamp': self.timestamp.isoformat()
        }
    
    def is_success(self) -> bool:
        """检查是否成功"""
        return self.error is None
    
    def is_cached(self) -> bool:
        """检查是否来自缓存"""
        return self.cached


class LabelerInterface(ABC):
    """Labeler 统一抽象接口"""
    
    def __init__(self, config: Any):
        """
        初始化 Labeler
        
        Args:
            config: 配置对象 (通常是 OmegaConf DictConfig)
        """
        self.config = config
        self.name = getattr(config.labeler_info, 'name', self.__class__.__name__)
    
    @abstractmethod
    def label(self, input_data: LabelerInput) -> LabelerOutput:
        """
        核心标注方法
        
        Args:
            input_data: 标准化输入数据
            
        Returns:
            标准化输出结果
        """
        pass
    
    def batch_label(self, input_batch: List[LabelerInput]) -> List[LabelerOutput]:
        """
        批量标注方法 (默认实现为逐个处理)
        
        Args:
            input_batch: 批量输入数据
            
        Returns:
            批量输出结果
        """
        return [self.label(input_data) for input_data in input_batch]
    
    def get_name(self) -> str:
        """获取 Labeler 名称"""
        return self.name
    
    def get_config(self) -> Any:
        """获取配置信息"""
        return self.config
    
    def validate_input(self, input_data: LabelerInput) -> bool:
        """
        验证输入数据 (可选实现)
        
        Args:
            input_data: 输入数据
            
        Returns:
            是否有效
        """
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查 (可选实现)
        
        Returns:
            健康状态信息
        """
        return {
            'status': 'healthy',
            'name': self.name,
            'timestamp': datetime.now().isoformat()
        }


class APILabelerInterface(LabelerInterface):
    """API 类型 Labeler 的抽象接口"""
    
    @abstractmethod
    def _make_api_call(self, input_data: LabelerInput) -> Dict[str, Any]:
        """
        执行 API 调用
        
        Args:
            input_data: 输入数据
            
        Returns:
            API 响应结果
        """
        pass
    
    @abstractmethod
    def _parse_api_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 API 响应
        
        Args:
            response: API 原始响应
            
        Returns:
            解析后的结果
        """
        pass


class LocalModelLabelerInterface(LabelerInterface):
    """本地模型 Labeler 的抽象接口"""
    
    @abstractmethod
    def _load_model(self) -> Any:
        """
        加载本地模型
        
        Returns:
            模型对象
        """
        pass
    
    @abstractmethod
    def _preprocess_input(self, input_data: LabelerInput) -> Any:
        """
        预处理输入数据
        
        Args:
            input_data: 输入数据
            
        Returns:
            预处理后的数据
        """
        pass
    
    @abstractmethod
    def _postprocess_output(self, model_output: Any) -> Dict[str, Any]:
        """
        后处理模型输出
        
        Args:
            model_output: 模型原始输出
            
        Returns:
            后处理后的结果
        """
        pass


class SoftwareLabelerInterface(LabelerInterface):
    """软件工具 Labeler 的抽象接口"""
    
    @abstractmethod
    def _execute_tool(self, input_data: LabelerInput) -> Dict[str, Any]:
        """
        执行软件工具
        
        Args:
            input_data: 输入数据
            
        Returns:
            工具执行结果
        """
        pass


# 异常类定义
class LabelerException(Exception):
    """Labeler 基础异常类"""
    pass


class ConfigurationError(LabelerException):
    """配置错误异常"""
    pass


class APIError(LabelerException):
    """API 调用错误异常"""
    pass


class ModelLoadError(LabelerException):
    """模型加载错误异常"""
    pass


class ValidationError(LabelerException):
    """验证错误异常"""
    pass


class CacheError(LabelerException):
    """缓存错误异常"""
    pass
